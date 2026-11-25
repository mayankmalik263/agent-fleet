"""Agent registration, status changes, usage and inspection."""

import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.enums import AgentStatus, EventSource, EventType, ProviderName
from ..core.errors import InvalidTransitionError, LimitExceededError, ValidationFailedError
from ..core.state_machine import AGENT_ACTIVE, AGENT_TERMINAL, RUN_TERMINAL, check_agent_transition
from ..core.time import utcnow
from ..models import Agent, AgentMessage, Run, RunEvent, Task
from ..repositories import scoped
from .events import EventService

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._\-]{0,119}$")
_MODEL = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,63}$")

_STATUS_EVENTS = {
    AgentStatus.WAITING: EventType.AGENT_WAITING,
    AgentStatus.COMPLETED: EventType.AGENT_COMPLETED,
    AgentStatus.FAILED: EventType.AGENT_FAILED,
}


def safe_name(value: str | None, fallback: str = "agent", limit: int = 120) -> str:
    """Turn an observed runtime name (for example 'plugin:reviewer') into a valid agent name."""
    cleaned = re.sub(r"[^A-Za-z0-9 ._\-]", "-", (value or "").strip())[:limit].strip(" .-_")
    return cleaned if cleaned and cleaned[0].isalnum() else fallback


def _check_token(value: str | None, field: str, pattern: re.Pattern[str] = _TOKEN) -> str:
    if value is None or not pattern.match(value.strip()):
        raise ValidationFailedError(
            f"{field} is invalid (letters, digits, space, '.', '_', '-'; max 120 characters)", details={"field": field}
        )
    return value.strip()


def ensure_run_open(run: Run) -> None:
    if run.status in RUN_TERMINAL:
        raise InvalidTransitionError(f"run is already {run.status}", details={"run_status": run.status.value})


class AgentService:
    def __init__(self, session: Session, workspace_id: str, source: EventSource):
        self.session = session
        self.workspace_id = workspace_id
        self.source = source
        self.events = EventService(session)

    def _active_workers(self, run: Run) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(Agent)
                .where(
                    Agent.run_id == run.id,
                    Agent.status.in_(list(AGENT_ACTIVE)),
                    Agent.parent_agent_id.is_not(None),
                )
            )
            or 0
        )

    def _check_capacity(self, run: Run, agent_has_parent: bool) -> None:
        if agent_has_parent and self._active_workers(run) >= run.max_concurrent_agents:
            raise LimitExceededError(
                f"this run allows at most {run.max_concurrent_agents} active subagents; "
                "wait for one to finish before starting another",
                details={"max_concurrent_agents": run.max_concurrent_agents},
            )

    def register(
        self,
        run_id: str,
        name: str,
        role: str,
        model_alias: str,
        parent_agent_id: str | None = None,
        *,
        status: AgentStatus | None = None,
        provider: str = ProviderName.CLAUDE_CODE_LOCAL.value,
        external_ref: str | None = None,
        idempotency_key: str | None = None,
        enforce_capacity: bool = True,
        may_become_root: bool = True,
    ) -> Agent:
        """Register an agent. enforce_capacity=False is for observed agents (runner stream, hooks):
        they already run, so Agent Fleet records them instead of refusing them."""
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        ensure_run_open(run)
        name = _check_token(name, "name")
        role = _check_token(role, "role").lower()
        model_alias = _check_token(model_alias, "model_alias", _MODEL)
        parent = None
        if scoped.optional_id(parent_agent_id, "parent_agent_id"):
            parent = scoped.get_agent(self.session, self.workspace_id, parent_agent_id or "", run.id)
        if external_ref:
            existing = scoped.agent_by_external_ref(self.session, run.id, external_ref)
            if existing is not None:
                return existing
        status = status or (AgentStatus.QUEUED if parent else AgentStatus.RUNNING)
        if status in AGENT_ACTIVE and enforce_capacity:
            self._check_capacity(run, parent is not None)

        now = utcnow()
        agent = Agent(
            workspace_id=self.workspace_id,
            run_id=run.id,
            name=name,
            role=role,
            model_alias=model_alias,
            provider=provider,
            parent_agent_id=parent.id if parent else None,
            status=status,
            external_ref=external_ref,
            tool_call_count=0,
            started_at=now if status in AGENT_ACTIVE else None,
        )
        self.session.add(agent)
        self.session.flush()
        if parent is None and run.root_agent_id is None and may_become_root:
            run.root_agent_id = agent.id
        payload = {"name": name, "role": role, "model_alias": model_alias, "status": status.value}
        self.events.emit(
            run,
            EventType.AGENT_CREATED,
            f"Agent {name} ({role}, {model_alias}) registered",
            source=self.source,
            agent_id=agent.id,
            parent_agent_id=agent.parent_agent_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        if status in AGENT_ACTIVE:
            self.events.emit(
                run,
                EventType.AGENT_STARTED,
                f"Agent {name} started",
                source=self.source,
                agent_id=agent.id,
                parent_agent_id=agent.parent_agent_id,
            )
        return agent

    def update_status(
        self,
        run_id: str,
        agent_id: str,
        status: AgentStatus | str,
        *,
        message: str | None = None,
        idempotency_key: str | None = None,
    ) -> Agent:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        agent = scoped.get_agent(self.session, self.workspace_id, agent_id, run.id)
        try:
            target = AgentStatus(status)
        except ValueError:
            allowed = ", ".join(s.value for s in AgentStatus)
            raise ValidationFailedError(f"invalid agent status {status!r}; expected one of: {allowed}") from None
        if agent.status == target:
            return agent
        check_agent_transition(agent.status, target)
        ensure_run_open(run)
        if target in AGENT_ACTIVE and agent.status not in AGENT_ACTIVE:
            self._check_capacity(run, agent.parent_agent_id is not None)

        previous = agent.status
        agent.status = target
        now = utcnow()
        etype = _STATUS_EVENTS.get(target, EventType.AGENT_STATUS_CHANGED)
        if target in AGENT_ACTIVE and agent.started_at is None:
            agent.started_at = now
            etype = EventType.AGENT_STARTED
        if target in AGENT_TERMINAL:
            agent.completed_at = now
            agent.current_task_id = None
        self.events.emit(
            run,
            etype,
            message or f"{agent.name}: {previous.value} -> {target.value}",
            source=self.source,
            agent_id=agent.id,
            parent_agent_id=agent.parent_agent_id,
            payload={"from": previous.value, "to": target.value},
            idempotency_key=idempotency_key,
        )
        return agent

    def add_usage(self, agent: Agent, input_tokens: int | None, output_tokens: int | None) -> None:
        if input_tokens is not None:
            agent.input_tokens = (agent.input_tokens or 0) + max(0, int(input_tokens))
        if output_tokens is not None:
            agent.output_tokens = (agent.output_tokens or 0) + max(0, int(output_tokens))

    def details(self, run_id: str, agent_id: str, *, limit: int = 50) -> dict[str, Any]:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        agent = scoped.get_agent(self.session, self.workspace_id, agent_id, run.id)
        parent = self.session.get(Agent, agent.parent_agent_id) if agent.parent_agent_id else None
        current_task = self.session.get(Task, agent.current_task_id) if agent.current_task_id else None
        children = list(self.session.scalars(select(Agent).where(Agent.parent_agent_id == agent.id)))
        messages = list(
            self.session.scalars(
                select(AgentMessage)
                .where(
                    AgentMessage.run_id == run.id,
                    or_(AgentMessage.sender_agent_id == agent.id, AgentMessage.receiver_agent_id == agent.id),
                )
                .order_by(AgentMessage.timestamp.desc())
                .limit(limit)
            )
        )[::-1]
        tool_events = list(
            self.session.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == run.id, RunEvent.agent_id == agent.id, RunEvent.event_type.like("tool.%"))
                .order_by(RunEvent.sequence_number.desc())
                .limit(limit)
            )
        )[::-1]
        tasks = list(
            self.session.scalars(
                select(Task).where(Task.run_id == run.id, Task.assigned_agent_id == agent.id).order_by(Task.created_at)
            )
        )
        return {
            "agent": agent,
            "parent": parent,
            "current_task": current_task,
            "children": children,
            "recent_messages": messages,
            "tool_events": tool_events,
            "tasks": tasks,
        }
