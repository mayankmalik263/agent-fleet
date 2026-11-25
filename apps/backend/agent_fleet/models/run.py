from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.enums import ExecutionMode, PermissionPolicy, ProviderName, RunSource, RunStatus
from ..core.time import utcnow
from ..database.base import Base
from ..database.types import UTCDateTime
from ._columns import created_at_column, enum_type, id_column


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_runs_status_created", "status", "created_at"),
    )

    id: Mapped[str] = id_column()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[RunSource] = mapped_column(enum_type(RunSource, "run_source"), nullable=False)
    execution_mode: Mapped[ExecutionMode] = mapped_column(enum_type(ExecutionMode, "execution_mode"), nullable=False)
    provider: Mapped[ProviderName] = mapped_column(enum_type(ProviderName, "provider_name"), nullable=False)
    root_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL", use_alter=True, name="fk_runs_root_agent_id_agents")
    )
    status: Mapped[RunStatus] = mapped_column(enum_type(RunStatus, "run_status"), nullable=False)
    workspace_path: Mapped[str | None] = mapped_column(Text)
    permission_policy: Mapped[PermissionPolicy] = mapped_column(
        enum_type(PermissionPolicy, "permission_policy"), nullable=False
    )
    orchestrator_model: Mapped[str] = mapped_column(String(32), nullable=False, default="sonnet")
    max_concurrent_agents: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)
    final_summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Execution coordination (database-backed job queue).
    runner_device_id: Mapped[str | None] = mapped_column(ForeignKey("runner_devices.id", ondelete="SET NULL"))
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Per-run event counter. Incremented atomically to give each event a unique, gap-free sequence number.
    event_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Usage as reported by the runtime. Costs from Claude Code are client-side estimates, not invoices.
    usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    @property
    def event_count(self) -> int:
        """Number of events in the run (sequence numbers have no gaps)."""
        return self.event_seq
