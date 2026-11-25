"""MCP tool definitions. Thin wrappers over RunStore; stdout is reserved for the protocol."""

import logging
import sys
from functools import wraps
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .models import EventType, Run, RunEvent, Source
from .store import RunStore

log = logging.getLogger("agent_fleet")

INSTRUCTIONS = """\
Agent Fleet records multi-agent runs for observability.
1. Call create_run once at the start of a task; keep the returned run_id.
2. Call append_run_event with event_type 'run.started', then record real work as it happens
   (agent.started / agent.completed, task.created / task.completed, message.sent).
3. Call finish_run with status 'completed' or 'failed' and a short summary at the end.
"""


def _tool_errors(fn):
    """Turn expected store errors into ToolErrors the model can read and correct."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, LookupError) as e:
            log.info("%s rejected: %s", fn.__name__, e)
            raise ToolError(str(e)) from e

    return wrapper


def build_server(store: RunStore) -> MCPServer:
    mcp = MCPServer("agent-fleet", instructions=INSTRUCTIONS)

    @mcp.tool()
    @_tool_errors
    def create_run(task: str, source: Source = Source.CLAUDE_CODE) -> Run:
        """Create a new run for a task. Records a run.created event. Returns the run with its run_id."""
        run = store.create_run(task, source)
        log.info("created run %s (%s)", run.run_id, run.source)
        return run

    @mcp.tool()
    @_tool_errors
    def append_run_event(
        run_id: str,
        event_type: EventType,
        message: str,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
        parent_agent_id: str | None = None,
        task_id: str | None = None,
    ) -> RunEvent:
        """Append an event to an open run. 'run.started' moves the run to running.
        run.created / run.completed / run.failed are recorded by create_run and finish_run."""
        return store.append_event(run_id, event_type, message, agent_id, payload, parent_agent_id, task_id)

    @mcp.tool()
    @_tool_errors
    def get_run(run_id: str) -> Run:
        """Get a run's current status, timestamps and summary."""
        return store.get_run(run_id)

    @mcp.tool()
    @_tool_errors
    def list_run_events(run_id: str) -> list[RunEvent]:
        """List all events of a run in chronological order."""
        return store.list_events(run_id)

    @mcp.tool()
    @_tool_errors
    def finish_run(run_id: str, status: Literal["completed", "failed"], summary: str | None = None) -> Run:
        """Close a run as completed or failed with an optional summary. Records run.completed / run.failed."""
        run = store.finish_run(run_id, status, summary)
        log.info("finished run %s as %s", run.run_id, run.status)
        return run

    return mcp


def main() -> None:
    # Logs go to stderr; stdout carries only MCP JSON-RPC messages.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    store = RunStore()
    log.info("agent-fleet MCP server starting, db=%s", store.db_path)
    build_server(store).run("stdio")


if __name__ == "__main__":
    main()
