"""Inter-agent messages and free-form run events."""

from typing import Any

from sqlalchemy.orm import Session

from ..core.enums import FREEFORM_EVENT_TYPES, EventSource, EventType, MessageType
from ..core.errors import ValidationFailedError
from ..core.redaction import redact_text, sanitize
from ..models import AgentMessage, RunEvent
from ..repositories import scoped
from .agents import ensure_run_open
from .events import EventService
from .runs import MAX_DESCRIPTION, _clean_text


class MessageService:
    def __init__(self, session: Session, workspace_id: str, source: EventSource):
        self.session = session
        self.workspace_id = workspace_id
        self.source = source
        self.events = EventService(session)

    def send(
        self,
        run_id: str,
        sender_agent_id: str,
        content: str,
        *,
        message_type: MessageType | str = "note",
        receiver_agent_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> AgentMessage:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        ensure_run_open(run)
        sender = scoped.get_agent(self.session, self.workspace_id, sender_agent_id, run.id)
        receiver = None
        if scoped.optional_id(receiver_agent_id, "receiver_agent_id"):
            receiver = scoped.get_agent(self.session, self.workspace_id, receiver_agent_id or "", run.id)
        task = None
        if scoped.optional_id(task_id, "task_id"):
            task = scoped.get_task(self.session, self.workspace_id, task_id or "", run.id)
        try:
            mtype = MessageType(message_type)
        except ValueError:
            allowed = ", ".join(m.value for m in MessageType)
            raise ValidationFailedError(f"invalid message_type; expected one of: {allowed}") from None
        text = _clean_text(content, "content", MAX_DESCRIPTION) or ""

        message = AgentMessage(
            workspace_id=self.workspace_id,
            run_id=run.id,
            sender_agent_id=sender.id,
            receiver_agent_id=receiver.id if receiver else None,
            task_id=task.id if task else None,
            message_type=mtype,
            content=redact_text(text, MAX_DESCRIPTION),
            metadata_json=sanitize(metadata) if metadata else None,
        )
        self.session.add(message)
        self.session.flush()
        target = f" to {receiver.name}" if receiver else ""
        self.events.emit(
            run,
            EventType.MESSAGE_SENT,
            f"{sender.name}{target}: {text[:240]}",
            source=self.source,
            agent_id=sender.id,
            parent_agent_id=sender.parent_agent_id,
            task_id=task.id if task else None,
            idempotency_key=idempotency_key,
            payload={
                "message_id": message.id,
                "receiver_agent_id": message.receiver_agent_id,
                "message_type": mtype.value,
            },
        )
        return message

    def append_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> RunEvent:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        ensure_run_open(run)
        try:
            etype = EventType(event_type)
        except ValueError:
            etype = None
        if etype not in FREEFORM_EVENT_TYPES:
            allowed = ", ".join(sorted(e.value for e in FREEFORM_EVENT_TYPES))
            raise ValidationFailedError(
                f"event_type {event_type!r} cannot be appended directly. Allowed: {allowed}. "
                "Use the dedicated tools for run, agent, task and message changes.",
                details={"field": "event_type"},
            )
        agent = None
        if scoped.optional_id(agent_id, "agent_id"):
            agent = scoped.get_agent(self.session, self.workspace_id, agent_id or "", run.id)
        task = None
        if scoped.optional_id(task_id, "task_id"):
            task = scoped.get_task(self.session, self.workspace_id, task_id or "", run.id)
        if payload is not None and not isinstance(payload, dict):
            raise ValidationFailedError("payload must be a JSON object")
        text = _clean_text(message, "message", 2_000) or ""
        return self.events.emit(
            run,
            etype,
            text,
            source=self.source,
            agent_id=agent.id if agent else None,
            parent_agent_id=agent.parent_agent_id if agent else None,
            task_id=task.id if task else None,
            payload=payload,
            idempotency_key=idempotency_key,
        )
