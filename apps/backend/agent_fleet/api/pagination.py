from typing import Annotated, Any

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..core.errors import ValidationFailedError

Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


def apply_sort(stmt: Select[Any], sort: str | None, columns: dict[str, Any], default: Any) -> Select[Any]:
    """sort=field or sort=-field (descending). Unknown fields are rejected."""
    if not sort:
        return stmt.order_by(default)
    descending = sort.startswith("-")
    name = sort.lstrip("-")
    if name not in columns:
        raise ValidationFailedError(f"cannot sort by {name!r}; allowed: {', '.join(sorted(columns))}")
    column = columns[name]
    return stmt.order_by(column.desc() if descending else column.asc())


def paginate(db: Session, stmt: Select[Any], limit: int, offset: int) -> tuple[list[Any], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = list(db.scalars(stmt.limit(limit).offset(offset)))
    return items, total
