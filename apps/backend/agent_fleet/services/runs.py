"""Run lifecycle: creation, state transitions, completion, failure, cancellation and snapshots."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.enums import (
    AgentStatus,
    ApprovalStatus,
    EventSource,
    EventType,
    ExecutionMode,
    PermissionPolicy,
    ProviderName,
    RunSource,
    RunStatus,
    TaskStatus,
)
from ..core.errors import RuntimeUnavailableError, ValidationFailedError
from ..core.redaction import redact_text
from ..core.state_machine import AGENT_TERMINAL, RUN_TERMINAL, TASK_TERMINAL, check_run_transition
from ..core.time import utcnow
from ..models import Agent, AgentMessage, ApprovalRequest, Run, RunEvent, Task
from ..repositories import scoped
from .events import EventService
from .workspace_paths import resolve_workspace_path

MODEL_ALIASES = ("sonnet", "haiku")
MAX_TITLE = 200
MAX_DESCRIPTION = 20_000


def _clean_text(value: str | None, field: str, limit: int, *, required: bool = True) -> str | None:
    if value is None or not value.strip():
        if required:
            raise ValidationFailedError(f"{field} must not be empty", details={"field": field})
        return None
    value = value.strip()
    if len(value) > limit:
        raise ValidationFailedError(f"{field} exceeds {limit} characters", details={"field": field})
    return value


@dataclass
class NewRun:
    task_description: str
    title: str | None = None
    source: RunSource = RunSource.DASHBOARD
    provider: ProviderName = ProviderName.CLAUDE_CODE_LOCAL
    workspace_path: str | None = None
    orchestrator_model: str = "sonnet"
    permission_policy: PermissionPolicy = PermissionPolicy.READ_ONLY
    max_concurrent_agents: int | None = None
    confirm_workspace_edit: bool = False
    session_id: str | None = None


class RunService:
    def __init__(self, session: Session, workspace_id: str, source: EventSource):
        self.session = session
        self.workspace_id = workspace_id
        self.source = source
        self.events = EventService(session)

    # ---------- creation ----------
    def create(self, data: NewRun) -> Run:
        scoped.get_workspace(self.session, self.workspace_id)
        description = _clean_text(data.task_description, "task_description", MAX_DESCRIPTION)
        assert description is not None
        title = _clean_text(data.title, "title", MAX_TITLE, required=False) or description.splitlines()[0][:80]
        if data.orchestrator_model not in MODEL_ALIASES:
            raise ValidationFailedError(f"orchestrator_model must be one of: {', '.join(MODEL_ALIASES)}")
        if data.provider != ProviderName.CLAUDE_CODE_LOCAL:
            # Never fall back to a different provider silently.
            raise RuntimeUnavailableError(
                "The Anthropic API provider is not available in local mode. Use the local Claude Code provider."
            )
        settings = get_settings()
        max_agents = (
            settings.max_concurrent_agents if data.max_concurrent_agents is None else data.max_concurrent_agents
        )
        if not 1 <= max_agents <= 20:
            raise ValidationFailedError("max_concurrent_agents must be between 1 and 20")

        workspace_path = resolve_workspace_path(data.workspace_path, settings)
        if data.permission_policy == PermissionPolicy.WORKSPACE_EDIT:
            # Runner-executed runs need explicit confirmation. For runs started inside Claude Code the
            # policy is informational: Claude Code's own permission settings govern that session.
            if data.source != RunSource.CLAUDE_CODE and not data.confirm_workspace_edit:
                raise ValidationFailedError(
                    "workspace_edit needs explicit confirmation (confirm_workspace_edit=true)",
                    details={"field": "confirm_workspace_edit"},
                )
            if workspace_path is None:
                raise ValidationFailedError(
                    "workspace_edit needs a workspace_path", details={"field": "workspace_path"}
                )

        runner_managed = data.source != RunSource.CLAUDE_CODE
        now = utcnow()
        run = Run(
            workspace_id=self.workspace_id,
            title=title,
            task_description=description,
            source=data.source,
            execution_mode=ExecutionMode.LOCAL_CLAUDE_CODE,
            provider=data.provider,
            status=RunStatus.QUEUED if runner_managed else RunStatus.RUNNING,
            workspace_path=workspace_path,
            permission_policy=data.permission_policy,
            orchestrator_model=data.orchestrator_model,
            max_concurrent_agents=max_agents,
            session_id=_clean_text(data.session_id, "session_id", 64, required=False),
            started_at=None if runner_managed else now,
            attempt_count=0,
            event_seq=0,
            cancel_requested=False,
        )
        self.session.add(run)
        self.session.flush()
        self.events.emit(
            run,
            EventType.RUN_CREATED,
            f"Run created: {title}",
            source=self.source,
            payload={
                "source": data.source.value,
                "permission_policy": data.permission_policy.value,
                "orchestrator_model": data.orchestrator_model,
            },
        )
        if data.permission_policy == PermissionPolicy.WORKSPACE_EDIT:
            approval = ApprovalRequest(
                workspace_id=self.workspace_id,
                run_id=run.id,
                action_type="workspace_edit",
                description=f"Allow file edits inside {workspace_path}",
                status=ApprovalStatus.APPROVED if data.confirm_workspace_edit else ApprovalStatus.PENDING,
                resolved_at=now if data.confirm_workspace_edit else None,
            )
            self.session.add(approval)
            self.session.flush()
            if data.confirm_workspace_edit:
                self.events.emit(
                    run,
                    EventType.APPROVAL_APPROVED,
                    "Workspace edit confirmed by the user",
                    source=self.source,
                    payload={"approval_id": approval.id},
                )
        if runner_managed:
            self.events.emit(run, EventType.RUN_QUEUED, "Run queued for the local runner", source=self.source)
        else:
            self.events.emit(run, EventType.RUN_STARTED, "Run started from Claude Code", source=self.source)
        return run

    # ---------- transitions ----------
    def transition(
        self,
        run: Run,
        target: RunStatus,
        message: str,
        *,
        payload: dict[str, Any] | None = None,
        event_type: EventType | None = None,
    ) -> Run:
        check_run_transition(run.status, target)
        previous = run.status
        run.status = target
        now = utcnow()
        if target in (RunStatus.PLANNING, RunStatus.RUNNING) and run.started_at is None:
            run.started_at = now
        if target in RUN_TERMINAL:
            run.completed_at = now
            run.lease_expires_at = None
        etype = event_type or {
            RunStatus.RUNNING: EventType.RUN_STARTED
            if previous in (RunStatus.QUEUED, RunStatus.PLANNING)
            else EventType.RUN_STATUS_CHANGED,
            RunStatus.COMPLETED: EventType.RUN_COMPLETED,
            RunStatus.FAILED: EventType.RUN_FAILED,
            RunStatus.CANCELLED: EventType.RUN_CANCELLED,
            RunStatus.QUEUED: EventType.RUN_QUEUED,
        }.get(target, EventType.RUN_STATUS_CHANGED)
        self.events.emit(
            run,
            etype,
            message,
            source=self.source,
            payload={"from": previous.value, "to": target.value, **(payload or {})},
        )
        return run

    def complete(self, run_id: str, final_summary: str) -> Run:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        summary = _clean_text(final_summary, "final_summary", MAX_DESCRIPTION)
        run.final_summary = redact_text(summary or "", MAX_DESCRIPTION)
        self.transition(
            run, RunStatus.COMPLETED, "Run completed", payload={"summary_preview": summary[:300] if summary else ""}
        )
        self.close_agents(run, AgentStatus.COMPLETED, "closed when the run completed")
        return run

    def fail(self, run_id: str, error_message: str) -> Run:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        error = _clean_text(error_message, "error_message", MAX_DESCRIPTION)
        run.error_message = redact_text(error or "", MAX_DESCRIPTION)
        self.transition(run, RunStatus.FAILED, f"Run failed: {(error or '')[:300]}")
        self.close_agents(run, AgentStatus.CANCELLED, "stopped because the run failed")
        self.close_tasks(run, "stopped because the run failed")
        return run

    def cancel(self, run_id: str, reason: str = "Cancelled by the user") -> Run:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        run.cancel_requested = True
        self.transition(run, RunStatus.CANCELLED, reason)
        self.close_agents(run, AgentStatus.CANCELLED, "stopped because the run was cancelled")
        self.close_tasks(run, "stopped because the run was cancelled")
        return run

    def close_agents(self, run: Run, status: AgentStatus, reason: str) -> None:
        """Agents that never reported an end are closed with a flag that says so (no invented outcome)."""
        agents = self.session.scalars(select(Agent).where(Agent.run_id == run.id)).all()
        now = utcnow()
        for agent in agents:
            if agent.status in AGENT_TERMINAL:
                continue
            explicit_root = agent.id == run.root_agent_id and status == AgentStatus.COMPLETED
            previous = agent.status
            agent.status = status
            agent.completed_at = now
            agent.current_task_id = None
            etype = EventType.AGENT_COMPLETED if status == AgentStatus.COMPLETED else EventType.AGENT_STATUS_CHANGED
            self.events.emit(
                run,
                etype,
                f"{agent.name} {reason}",
                source=self.source,
                agent_id=agent.id,
                parent_agent_id=agent.parent_agent_id,
                payload={"from": previous.value, "to": status.value, "implicit": not explicit_root},
            )

    def close_tasks(self, run: Run, reason: str) -> None:
        tasks = self.session.scalars(select(Task).where(Task.run_id == run.id)).all()
        now = utcnow()
        for task in tasks:
            if task.status in TASK_TERMINAL:
                continue
            previous = task.status
            task.status = TaskStatus.CANCELLED
            task.completed_at = now
            self.events.emit(
                run,
                EventType.TASK_STATUS_CHANGED,
                f"Task '{task.title}' {reason}",
                source=self.source,
                task_id=task.id,
                agent_id=task.assigned_agent_id,
                payload={"from": previous.value, "to": TaskStatus.CANCELLED.value, "implicit": True},
            )

    # ---------- reads ----------
    def snapshot(self, run_id: str, *, recent_messages: int = 50) -> dict[str, Any]:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        agents = list(self.session.scalars(select(Agent).where(Agent.run_id == run.id).order_by(Agent.created_at)))
        tasks = list(self.session.scalars(select(Task).where(Task.run_id == run.id).order_by(Task.created_at)))
        messages = list(
            self.session.scalars(
                select(AgentMessage)
                .where(AgentMessage.run_id == run.id)
                .order_by(AgentMessage.timestamp.desc())
                .limit(recent_messages)
            )
        )[::-1]
        event_counts = dict(
            self.session.execute(
                select(RunEvent.event_type, func.count()).where(RunEvent.run_id == run.id).group_by(RunEvent.event_type)
            ).all()
        )
        return {
            "run": run,
            "agents": agents,
            "hierarchy": build_hierarchy(agents),
            "tasks": tasks,
            "recent_messages": messages,
            "event_counts": event_counts,
            "total_events": run.event_seq,
            "agent_status_counts": _count(a.status.value for a in agents),
            "task_status_counts": _count(t.status.value for t in tasks),
        }


def _count(values: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def build_hierarchy(agents: list[Agent]) -> list[dict[str, Any]]:
    """Nested tree of agents by parent_agent_id. Agents whose parent is unknown become roots."""
    ids = {a.id for a in agents}
    children: dict[str | None, list[Agent]] = {}
    for agent in agents:
        key = agent.parent_agent_id if agent.parent_agent_id in ids else None
        children.setdefault(key, []).append(agent)

    def node(agent: Agent, depth: int) -> dict[str, Any]:
        kids = children.get(agent.id, []) if depth < 50 else []
        return {"agent_id": agent.id, "name": agent.name, "children": [node(k, depth + 1) for k in kids]}

    return [node(a, 0) for a in children.get(None, [])]
