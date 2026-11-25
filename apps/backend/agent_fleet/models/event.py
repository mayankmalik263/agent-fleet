from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.enums import EventSource
from ..core.time import utcnow
from ..database.base import Base
from ..database.types import UTCDateTime
from ._columns import enum_type, id_column


class RunEvent(Base):
    """Append-only event history. The source of truth for timelines, replay and SSE."""

    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_number"),
        UniqueConstraint("run_id", "idempotency_key"),
        Index("ix_run_events_run_timestamp", "run_id", "timestamp"),
        Index("ix_run_events_workspace_timestamp", "workspace_id", "timestamp"),
    )

    id: Mapped[str] = id_column()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Agent and task references become NULL if those rows are removed; the event itself is kept.
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    parent_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source: Mapped[EventSource] = mapped_column(enum_type(EventSource, "event_source"), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))

    @property
    def payload(self) -> dict[str, Any] | None:
        return self.payload_json
