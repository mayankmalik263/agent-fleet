from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.enums import AgentStatus
from ..database.base import Base
from ..database.types import UTCDateTime
from ._columns import created_at_column, enum_type, id_column


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agents_run_created", "run_id", "created_at"),
        # external_ref links an agent to a runtime identity, e.g. the Claude Code Agent tool_use id.
        UniqueConstraint("run_id", "external_ref"),
    )

    id: Mapped[str] = id_column()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    model_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    status: Mapped[AgentStatus] = mapped_column(enum_type(AgentStatus, "agent_status"), nullable=False)
    current_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL", use_alter=True, name="fk_agents_current_task_id_tasks")
    )
    external_ref: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = created_at_column()
