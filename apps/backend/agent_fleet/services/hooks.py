"""Claude Code hook events for runs started inside Claude Code (Mode B).

The SessionStart hook tells Claude its session id; Claude passes it to create_run(session_id=...).
Later hook events with that session id are attached to the run. Unlinked events are ignored.
Only non-sensitive metadata is stored: ids, agent type, tool name. Tool inputs and outputs are not stored.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.enums import AgentStatus, EventSource, EventType, ProviderName
from ..core.state_machine import AGENT_TERMINAL, RUN_TERMINAL
from ..models import Run
from ..repositories import scoped
from .agents import AgentService, safe_name
from .events import EventService

HOOK_EVENTS = {"SubagentStart", "SubagentStop", "PostToolUseFailure", "SessionEnd"}


def _short(value: Any, limit: int = 120) -> str | None:
    return None if value is None else str(value)[:limit]


def record_hook_event(session: Session, workspace_id: str, data: dict[str, Any]) -> dict[str, Any]:
    name = data.get("hook_event_name")
    session_id = _short(data.get("session_id"), 64)
    if name not in HOOK_EVENTS or not session_id:
        return {"linked": False, "reason": "event not tracked"}
    run = session.scalars(
        select(Run)
        .where(Run.workspace_id == workspace_id, Run.session_id == session_id)
        .order_by(Run.created_at.desc())
        .limit(1)
    ).first()
    if run is None or run.status in RUN_TERMINAL:
        return {"linked": False, "reason": "no open run for this session"}

    events = EventService(session)
    agents = AgentService(session, workspace_id, EventSource.HOOK)
    claude_agent_id = _short(data.get("agent_id"))
    agent_type = safe_name(_short(data.get("agent_type")), "subagent")
    ref = f"hook:{claude_agent_id}" if claude_agent_id else None
    key = f"hook:{name}:{claude_agent_id or ''}:{_short(data.get('tool_use_id')) or ''}"

    if name == "SubagentStart" and ref:
        agent = scoped.agent_by_external_ref(session, run.id, ref)
        if agent is None:
            agents.register(
                run.id,
                agent_type[:120],
                agent_type[:64],
                "inherit",
                run.root_agent_id,
                status=AgentStatus.RUNNING,
                provider=ProviderName.CLAUDE_CODE_LOCAL.value,
                external_ref=ref,
                idempotency_key=key,
                enforce_capacity=False,
                may_become_root=False,
            )
    elif name == "SubagentStop" and ref:
        agent = scoped.agent_by_external_ref(session, run.id, ref)
        if agent is not None and agent.status not in AGENT_TERMINAL:
            agents.update_status(
                run.id, agent.id, AgentStatus.COMPLETED, message=f"{agent.name} finished", idempotency_key=key
            )
    elif name == "PostToolUseFailure":
        agent = scoped.agent_by_external_ref(session, run.id, ref) if ref else None
        events.emit(
            run,
            EventType.TOOL_FAILED,
            f"Tool {_short(data.get('tool_name'), 80)} failed",
            source=EventSource.HOOK,
            agent_id=agent.id if agent else run.root_agent_id,
            payload={"tool_name": _short(data.get("tool_name"), 80), "tool_use_id": _short(data.get("tool_use_id"))},
            idempotency_key=key,
        )
    elif name == "SessionEnd":
        events.emit(
            run,
            EventType.EXECUTION_SESSION_ENDED,
            "Claude Code session ended",
            source=EventSource.HOOK,
            payload={"reason": _short(data.get("reason"), 80)},
            idempotency_key=f"hook:SessionEnd:{session_id}",
        )
    return {"linked": True, "run_id": run.id}
