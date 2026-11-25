from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.enums import TaskPriority, TaskStatus
from ..core.time import utcnow
from ..database.base import Base
from ..database.types import UTCDateTime
from ._columns import created_at_column, enum_type, id_column


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_run_status", "run_id", "status"),
        CheckConstraint(
            "progress_percentage IS NULL OR (progress_percentage >= 0 AND progress_percentage <= 100)",
            name="progress_range",
        ),
    )

    id: Mapped[str] = id_column()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable so task history survives if an agent row is ever removed.
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), index=True)
    created_by_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    parent_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    priority: Mapped[TaskPriority] = mapped_column(enum_type(TaskPriority, "task_priority"), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(enum_type(TaskStatus, "task_status"), nullable=False)
    # NULL means "not reported". The UI shows progress only when an agent reported a real value.
    progress_percentage: Mapped[int | None] = mapped_column(Integer)
    result_summary: Mapped[str | None] = mapped_column(Text)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
