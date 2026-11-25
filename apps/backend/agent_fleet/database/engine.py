"""Engine and session factory. SQLite runs in WAL mode with IMMEDIATE transactions so the API,
the runner and MCP server processes can write to the same file without lost updates."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import get_settings


def build_engine(database_url: str, *, busy_timeout_ms: int = 15_000) -> Engine:
    if not database_url.startswith("sqlite"):
        return create_engine(database_url, pool_pre_ping=True)

    path = database_url.split("///", 1)[-1]
    if path and path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args={"timeout": busy_timeout_ms / 1000})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):
        # Take over BEGIN from sqlite3 (SQLAlchemy documented recipe) so we can use BEGIN IMMEDIATE.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn):
        # Write sessions use IMMEDIATE: they take the write lock at the start, so a read-then-write
        # transaction never fails with SQLITE_BUSY_SNAPSHOT when another process wrote in between.
        # Read-only sessions use DEFERRED and never block writers (WAL mode).
        mode = conn.get_execution_options().get("sqlite_begin", "IMMEDIATE")
        conn.exec_driver_sql("BEGIN DEFERRED" if mode == "DEFERRED" else "BEGIN IMMEDIATE")

    return engine


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return build_engine(settings.database_url, busy_timeout_ms=settings.sqlite_busy_timeout_ms)


@lru_cache
def _session_factory(engine: Engine, readonly: bool = False) -> sessionmaker[Session]:
    bind = engine.execution_options(sqlite_begin="DEFERRED") if readonly else engine
    return sessionmaker(bind=bind, expire_on_commit=False)


def get_session_factory(engine: Engine | None = None, *, readonly: bool = False) -> sessionmaker[Session]:
    return _session_factory(engine or get_engine(), readonly)


@contextmanager
def session_scope(factory: sessionmaker[Session] | None = None, *, readonly: bool = False) -> Iterator[Session]:
    """One transaction: commit on success, roll back on any error."""
    session = (factory or get_session_factory(readonly=readonly))()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
