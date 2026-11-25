import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from ..core.time import ensure_utc


class UTCDateTime(TypeDecorator[datetime]):
    """Stores UTC; always returns timezone-aware UTC datetimes (SQLite drops the offset)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return ensure_utc(value)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return ensure_utc(value)


def new_id() -> str:
    return str(uuid.uuid4())
