from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.enums import ProviderConnectionStatus, RunnerStatus
from ..core.time import utcnow
from ..database.base import Base
from ..database.types import UTCDateTime
from ._columns import created_at_column, enum_type, id_column


class RunnerDevice(Base):
    __tablename__ = "runner_devices"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    id: Mapped[str] = id_column()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    runtime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[RunnerStatus] = mapped_column(enum_type(RunnerStatus, "runner_status"), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = created_at_column()


class ProviderConnection(Base):
    """Future BYOK provider credentials. Local Claude Code mode never needs a row here."""

    __tablename__ = "provider_connections"
    __table_args__ = (UniqueConstraint("workspace_id", "provider"),)

    id: Mapped[str] = id_column()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ProviderConnectionStatus] = mapped_column(
        enum_type(ProviderConnectionStatus, "provider_connection_status"), nullable=False
    )
    # Ciphertext only. No code path writes plaintext credentials; see docs/SECURITY.md.
    encrypted_credentials: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)
