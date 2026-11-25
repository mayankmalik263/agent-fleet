from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base
from ._columns import created_at_column, id_column

# Local single-user mode uses one fixed user and workspace, seeded by the first migration.
LOCAL_USER_ID = "00000000-0000-4000-8000-000000000001"
LOCAL_WORKSPACE_ID = "00000000-0000-4000-8000-000000000002"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = id_column()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = id_column()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = created_at_column()
