from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.enums import ApprovalStatus
from ..database.base import Base
from ..database.types import UTCDateTime
from ._columns import created_at_column, enum_type, id_column


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = id_column()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    # NULL when the request comes from a person (for example the dashboard edit confirmation).
    requested_by_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(enum_type(ApprovalStatus, "approval_status"), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
