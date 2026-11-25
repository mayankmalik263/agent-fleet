"""Agent Fleet MCP server (stdio by default).

The tools are thin adapters over the same services the REST API uses; no business rules live here.
stdout carries only MCP JSON-RPC messages; all diagnostics go to stderr.

Scope rules:
- The server is bound to one workspace (AGENT_FLEET_WORKSPACE_ID, default: the local workspace).
  Records of other workspaces are reported as "not found".
- When the local runner starts Claude Code for a run, it sets AGENT_FLEET_RUN_ID. The session can then
  touch only that run and cannot create new runs (this prevents runaway recursive runs).
"""

import logging
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Literal, ParamSpec, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import get_settings
from ..core.enums import (
    AgentStatus,
    EventSource,
    MessageType,
    PermissionPolicy,
    RunSource,
    TaskPriority,
    TaskStatus,
)
from ..core.errors import AgentFleetError
from ..core.logging import configure_logging
from ..database import get_session_factory, session_scope
from ..database.migrate import upgrade
from ..integrations import graphify
from ..models import LOCAL_WORKSPACE_ID
from ..repositories import scoped
from ..schemas import AgentDetails, EventRead, RunSnapshot, TaskRead
from ..services.agents import AgentService
from ..services.messages import MessageService
from ..services.runs import NewRun, RunService
from ..services.tasks import TaskService

log = logging.getLogger("agent_fleet.mcp")

P = ParamSpec("P")
R = TypeVar("R")

INSTRUCTIONS = """\
Agent Fleet records multi-agent work so people can watch it live in the dashboard.
Use these tools to report REAL activity only. Never invent progress, counts or results.
Typical flow: create_run (skip if you were given a run_id) -> register_agent for yourself (no parent)
-> register_agent for each subagent you delegate to (parent_agent_id = your agent_id) -> create_task
-> update_task_status / send_agent_message while work happens -> submit_task_result -> complete_run
(or fail_run). Progress percentages are optional: report them only when you can measure them.
"""


class RunCreated(BaseModel):
    run_id: str
    status: str
    created_at: datetime


class AgentRef(BaseModel):
    agent_id: str
    status: str


class TaskRef(BaseModel):
    task_id: str
    status: str
    progress_percentage: int | None


class MessageRef(BaseModel):
    message_id: str
    timestamp: datetime


class RunRef(BaseModel):
    run_id: str
    status: str
    completed_at: datetime | None


class ToolContext:
    def __init__(self, workspace_id: str, bound_run_id: str | None, factory: sessionmaker[Session] | None = None):
        self.workspace_id = workspace_id
        self.bound_run_id = bound_run_id
        self.factory = factory

    @contextmanager
    def session(self) -> Iterator[Session]:
        with session_scope(self.factory or get_session_factory()) as session:
            yield session

    def check_run(self, run_id: str) -> str:
        run_id = scoped.parse_id(run_id, "run_id")
        if self.bound_run_id and run_id != self.bound_run_id:
            raise ToolError(f"not_found: this session may only access run {self.bound_run_id}")
        return run_id


def _tool_errors(fn: Callable[P, R]) -> Callable[P, R]:
    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except AgentFleetError as exc:
            log.info("%s rejected: %s %s", fn.__name__, exc.code, exc.message)
            raise ToolError(f"{exc.code}: {exc.message}") from exc

    return wrapper


def build_server(ctx: ToolContext) -> MCPServer:
    mcp = MCPServer("agent-fleet", instructions=INSTRUCTIONS)
    src = EventSource.MCP

    @mcp.tool()
    @_tool_errors
    def create_run(
        task_description: str,
        source: Literal["claude_code", "dashboard", "api"] = "claude_code",
        workspace_id: str | None = None,
        title: str | None = None,
        session_id: str | None = None,
    ) -> RunCreated:
        """Create a run. source=claude_code (default) starts a run that this Claude Code session reports on
        itself. source=dashboard or api queues the run for the local runner instead.
        session_id: optional Claude Code session id, so Claude Code hooks can attach lifecycle events."""
        if ctx.bound_run_id:
            raise ToolError(f"conflict: this session already belongs to run {ctx.bound_run_id}; do not create runs")
        if workspace_id and scoped.parse_id(workspace_id, "workspace_id") != ctx.workspace_id:
            raise ToolError("not_found: cross-workspace access is not allowed")
        with ctx.session() as s:
            run = RunService(s, ctx.workspace_id, src).create(
                NewRun(
                    task_description=task_description,
                    title=title,
                    source=RunSource(source),
                    permission_policy=PermissionPolicy.READ_ONLY,
                    session_id=session_id,
                )
            )
            return RunCreated(run_id=run.id, status=run.status.value, created_at=run.created_at)

    @mcp.tool()
    @_tool_errors
    def register_agent(
        run_id: str, name: str, role: str, model_alias: str, parent_agent_id: str | None = None
    ) -> AgentRef:
        """Register an agent in a run. Without parent_agent_id the agent is a root (normally the orchestrator)
        and starts as running. With a parent it starts as queued; set it to running when it starts work.
        model_alias: the Claude model alias in use, for example sonnet or haiku."""
        with ctx.session() as s:
            agent = AgentService(s, ctx.workspace_id, src).register(
                ctx.check_run(run_id), name, role, model_alias, parent_agent_id
            )
            return AgentRef(agent_id=agent.id, status=agent.status.value)

    @mcp.tool()
    @_tool_errors
    def update_agent_status(run_id: str, agent_id: str, status: AgentStatus) -> AgentRef:
        """Change an agent's status (idle, queued, running, waiting, reviewing, completed, failed, cancelled).
        Completed, failed and cancelled are final."""
        with ctx.session() as s:
            agent = AgentService(s, ctx.workspace_id, src).update_status(ctx.check_run(run_id), agent_id, status)
            return AgentRef(agent_id=agent.id, status=agent.status.value)

    @mcp.tool()
    @_tool_errors
    def create_task(
        run_id: str,
        title: str,
        description: str,
        assigned_agent_id: str,
        parent_task_id: str | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        created_by_agent_id: str | None = None,
    ) -> TaskRef:
        """Record a delegated task. created_by_agent_id defaults to the assigned agent's parent."""
        with ctx.session() as s:
            task = TaskService(s, ctx.workspace_id, src).create(
                ctx.check_run(run_id),
                title,
                description,
                assigned_agent_id,
                created_by_agent_id=created_by_agent_id,
                parent_task_id=parent_task_id,
                priority=priority,
            )
            return TaskRef(task_id=task.id, status=task.status.value, progress_percentage=task.progress_percentage)

    @mcp.tool()
    @_tool_errors
    def update_task_status(
        run_id: str, task_id: str, status: TaskStatus, progress_percentage: int | None = None
    ) -> TaskRef:
        """Change a task's status (pending, in_progress, blocked, review, completed, failed, cancelled).
        progress_percentage (0-100) is optional: give it only when you can measure progress."""
        with ctx.session() as s:
            task = TaskService(s, ctx.workspace_id, src).update_status(
                ctx.check_run(run_id), task_id, status, progress_percentage
            )
            return TaskRef(task_id=task.id, status=task.status.value, progress_percentage=task.progress_percentage)

    @mcp.tool()
    @_tool_errors
    def submit_task_result(
        run_id: str, task_id: str, agent_id: str, result_summary: str, result_payload: dict[str, Any] | None = None
    ) -> TaskRead:
        """Submit the public result of a task and mark it completed. Put structured findings in
        result_payload (a JSON object). Do not include hidden reasoning or secrets."""
        with ctx.session() as s:
            task = TaskService(s, ctx.workspace_id, src).submit_result(
                ctx.check_run(run_id), task_id, agent_id, result_summary, result_payload
            )
            return TaskRead.model_validate(task)

    @mcp.tool()
    @_tool_errors
    def send_agent_message(
        run_id: str,
        sender_agent_id: str,
        content: str,
        message_type: MessageType = MessageType.NOTE,
        receiver_agent_id: str | None = None,
        task_id: str | None = None,
    ) -> MessageRef:
        """Record a message from one agent to another (or to the whole run when receiver is omitted)."""
        with ctx.session() as s:
            msg = MessageService(s, ctx.workspace_id, src).send(
                ctx.check_run(run_id),
                sender_agent_id,
                content,
                message_type=message_type,
                receiver_agent_id=receiver_agent_id,
                task_id=task_id,
            )
            return MessageRef(message_id=msg.id, timestamp=msg.timestamp)

    @mcp.tool()
    @_tool_errors
    def append_run_event(
        run_id: str,
        event_type: str,
        message: str,
        agent_id: str | None = None,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> EventRead:
        """Append an observational event. Allowed event_type values: agent.waiting, task.progress,
        message.received, tool.started, tool.completed, tool.failed, execution.notice.
        State changes have dedicated tools (register_agent, update_task_status, complete_run, ...)."""
        with ctx.session() as s:
            event = MessageService(s, ctx.workspace_id, src).append_event(
                ctx.check_run(run_id), event_type, message, agent_id=agent_id, task_id=task_id, payload=payload
            )
            return EventRead.model_validate(event)

    @mcp.tool()
    @_tool_errors
    def get_run_snapshot(run_id: str) -> RunSnapshot:
        """Current run state: run details, agents, agent hierarchy, tasks, recent messages, event counts
        and status counts."""
        with ctx.session() as s:
            return RunSnapshot.model_validate(RunService(s, ctx.workspace_id, src).snapshot(ctx.check_run(run_id)))

    @mcp.tool()
    @_tool_errors
    def get_agent_details(run_id: str, agent_id: str) -> AgentDetails:
        """One agent with its parent, current task, children, recent messages, tool activity and tasks."""
        with ctx.session() as s:
            return AgentDetails.model_validate(
                AgentService(s, ctx.workspace_id, src).details(ctx.check_run(run_id), agent_id)
            )

    @mcp.tool()
    @_tool_errors
    def complete_run(run_id: str, final_summary: str) -> RunRef:
        """Mark the run completed with its final public summary. Call this once, at the end."""
        with ctx.session() as s:
            run = RunService(s, ctx.workspace_id, src).complete(ctx.check_run(run_id), final_summary)
            return RunRef(run_id=run.id, status=run.status.value, completed_at=run.completed_at)

    @mcp.tool()
    @_tool_errors
    def fail_run(run_id: str, error_message: str) -> RunRef:
        """Mark the run failed with a short, public error description."""
        with ctx.session() as s:
            run = RunService(s, ctx.workspace_id, src).fail(ctx.check_run(run_id), error_message)
            return RunRef(run_id=run.id, status=run.status.value, completed_at=run.completed_at)

    @mcp.tool()
    @_tool_errors
    def query_code_graph(
        run_id: str, command: Literal["query", "path", "explain"], arguments: list[str]
    ) -> dict[str, Any]:
        """Optional: ask the local Graphify code knowledge graph of the run's workspace (read-only).
        query: ["question"]; path: ["A", "B"]; explain: ["Name"]. Fails clearly if Graphify or its graph
        (graphify-out/graph.json) is not available."""
        with ctx.session() as s:
            run = scoped.get_run(s, ctx.workspace_id, ctx.check_run(run_id))
            workspace = run.workspace_path
        if not workspace:
            raise ToolError("unavailable: this run has no workspace_path")
        try:
            return graphify.run_query(Path(workspace), command, arguments)
        except (ValueError, RuntimeError) as exc:
            raise ToolError(f"unavailable: {exc}") from exc

    return mcp


def context_from_env() -> ToolContext:
    workspace_id = os.environ.get("AGENT_FLEET_WORKSPACE_ID") or LOCAL_WORKSPACE_ID
    bound = os.environ.get("AGENT_FLEET_RUN_ID") or None
    return ToolContext(workspace_id=workspace_id, bound_run_id=bound)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    transport = os.environ.get("AGENT_FLEET_MCP_TRANSPORT", "stdio")
    if transport != "stdio":
        # A remote transport needs real authentication first (see docs/MCP_INTEGRATION.md).
        sys.exit("Only the local stdio transport is enabled. Remote MCP needs authentication and is not enabled.")
    upgrade()
    ctx = context_from_env()
    log.info("agent-fleet MCP server starting (stdio), workspace=%s bound_run=%s", ctx.workspace_id, ctx.bound_run_id)
    build_server(ctx).run("stdio")


if __name__ == "__main__":
    main()
