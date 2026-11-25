"""EventService: the only writer of run_events.

Order of operations for every event:
1. The caller changes state and calls emit() inside the same transaction.
2. emit() takes the next per-run sequence number with one atomic UPDATE ... RETURNING.
3. The caller's transaction commits. The event is now durable.
4. SSE subscribers in any process read it by polling run_events with sequence_number > cursor.
Idempotency keys make retried writes (for example a re-parsed stream line) a no-op.
"""

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core.enums import EventSource, EventType
from ..core.redaction import redact_text, sanitize
from ..core.time import utcnow
from ..models import Run, RunEvent

MAX_EVENT_MESSAGE = 2_000


class EventService:
    def __init__(self, session: Session):
        self.session = session

    def emit(
        self,
        run: Run,
        event_type: EventType | str,
        message: str,
        *,
        source: EventSource,
        agent_id: str | None = None,
        parent_agent_id: str | None = None,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> RunEvent:
        if idempotency_key:
            existing = self.session.scalars(
                select(RunEvent).where(RunEvent.run_id == run.id, RunEvent.idempotency_key == idempotency_key)
            ).one_or_none()
            if existing is not None:
                return existing

        seq = self.session.execute(
            update(Run)
            .where(Run.id == run.id)
            .values(event_seq=Run.event_seq + 1)
            .returning(Run.event_seq)
            .execution_options(synchronize_session=False)
        ).scalar_one()
        run.event_seq = seq

        event = RunEvent(
            workspace_id=run.workspace_id,
            run_id=run.id,
            sequence_number=seq,
            event_type=str(event_type),
            agent_id=agent_id,
            parent_agent_id=parent_agent_id,
            task_id=task_id,
            timestamp=utcnow(),
            message=redact_text(message, MAX_EVENT_MESSAGE),
            payload_json=sanitize(payload) if payload else None,
            source=source,
            idempotency_key=idempotency_key,
        )
        self.session.add(event)
        self.session.flush()
        return event


def events_after(
    session: Session, workspace_id: str, run_id: str, after_sequence: int = 0, limit: int = 500
) -> list[RunEvent]:
    return list(
        session.scalars(
            select(RunEvent)
            .where(
                RunEvent.workspace_id == workspace_id,
                RunEvent.run_id == run_id,
                RunEvent.sequence_number > after_sequence,
            )
            .order_by(RunEvent.sequence_number)
            .limit(limit)
        )
    )
