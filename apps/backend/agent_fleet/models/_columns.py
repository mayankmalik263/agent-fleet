from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.time import utcnow
from ..database.types import UTCDateTime, new_id


def enum_type(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """VARCHAR plus a CHECK constraint (portable between SQLite and PostgreSQL)."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def id_column() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(UTCDateTime(), nullable=False, default=utcnow)
