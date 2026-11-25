from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.enums import MessageType
from ..core.time import utcnow
from ..database.base import Base
from ..database.types import UTCDateTime
from ._columns import enum_type, id_column


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (Index("ix_agent_messages_run_timestamp", "run_id", "timestamp"),)

    id: Mapped[str] = id_column()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    sender_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    receiver_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    message_type: Mapped[MessageType] = mapped_column(enum_type(MessageType, "message_type"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
