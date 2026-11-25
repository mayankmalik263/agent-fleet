"""SQLite persistence for runs and run events. No MCP code lives here."""

import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import (
    LIFECYCLE_EVENTS,
    TERMINAL_STATUSES,
    EventType,
    Run,
    RunEvent,
    RunStatus,
    Source,
)

DB_PATH_ENV = "AGENT_FLEET_DB_PATH"
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "agent_fleet.db"

MAX_TEXT_LEN = 10_000
MAX_PAYLOAD_BYTES = 100_000

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    task        TEXT NOT NULL,
    source      TEXT NOT NULL CHECK (source IN ({", ".join(f"'{s}'" for s in Source)})),
    status      TEXT NOT NULL CHECK (status IN ({", ".join(f"'{s}'" for s in RunStatus)})),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    summary     TEXT
);

CREATE TABLE IF NOT EXISTS run_events (
    event_id         TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    event_type       TEXT NOT NULL CHECK (event_type IN ({", ".join(f"'{e}'" for e in EventType)})),
    agent_id         TEXT,
    parent_agent_id  TEXT,
    task_id          TEXT,
    message          TEXT NOT NULL,
    payload_json     TEXT,
    timestamp        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_run_events_run_ts ON run_events (run_id, timestamp);
"""
# ponytail: CHECK constraints are baked in at table creation; adding an enum member to an
# existing DB needs a migration (or drop data/agent_fleet.db while still in milestone 1).


class RunNotFoundError(LookupError):
    pass


class RunStateError(ValueError):
    pass


def default_db_path() -> Path:
    return Path(os.environ.get(DB_PATH_ENV) or DEFAULT_DB_PATH)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(name: str, value: str | None, *, optional: bool = False) -> str | None:
    if value is None or not value.strip():
        if optional:
            return None
        raise ValueError(f"{name} must not be empty")
    value = value.strip()
    if len(value) > MAX_TEXT_LEN:
        raise ValueError(f"{name} exceeds {MAX_TEXT_LEN} characters")
    return value


def _run_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"run_id is not a valid UUID: {value!r}") from None


def _enum(enum_cls, name: str, value):
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(e.value for e in enum_cls)
        raise ValueError(f"invalid {name} {value!r}; expected one of: {allowed}") from None


class RunStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA)
        finally:
            conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """One connection per operation, inside an IMMEDIATE (write-locked) transaction."""
        conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def _get_run_row(self, conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFoundError(f"run not found: {run_id}")
        return row

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        event_type: EventType,
        message: str,
        payload: dict[str, Any] | None = None,
        agent_id: str | None = None,
        parent_agent_id: str | None = None,
        task_id: str | None = None,
    ) -> RunEvent:
        payload_json = None
        if payload is not None:
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            try:
                payload_json = json.dumps(payload)
            except (TypeError, ValueError) as e:
                raise ValueError(f"payload is not JSON-serializable: {e}") from None
            if len(payload_json.encode()) > MAX_PAYLOAD_BYTES:
                raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
        event = RunEvent(
            event_id=str(uuid.uuid4()),
            run_id=run_id,
            event_type=event_type,
            agent_id=agent_id,
            parent_agent_id=parent_agent_id,
            task_id=task_id,
            message=message,
            payload=payload,
            timestamp=_now(),
        )
        conn.execute(
            "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id, run_id, event_type.value, agent_id, parent_agent_id,
                task_id, message, payload_json, event.timestamp.isoformat(),
            ),
        )
        return event

    def create_run(self, task: str, source: str) -> Run:
        task = _text("task", task)
        source = _enum(Source, "source", source)
        run_id, now = str(uuid.uuid4()), _now()
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (run_id, task, source.value, RunStatus.CREATED.value, now, now),
            )
            self._insert_event(conn, run_id, EventType.RUN_CREATED, "Run created", {"source": source.value})
            return Run(**self._get_run_row(conn, run_id))

    def append_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
        parent_agent_id: str | None = None,
        task_id: str | None = None,
    ) -> RunEvent:
        run_id = _run_id(run_id)
        event_type = _enum(EventType, "event_type", event_type)
        if event_type in LIFECYCLE_EVENTS:
            raise ValueError(f"{event_type} is recorded by create_run/finish_run, not appended directly")
        message = _text("message", message)
        agent_id = _text("agent_id", agent_id, optional=True)
        parent_agent_id = _text("parent_agent_id", parent_agent_id, optional=True)
        task_id = _text("task_id", task_id, optional=True)
        with self._tx() as conn:
            status = RunStatus(self._get_run_row(conn, run_id)["status"])
            if status in TERMINAL_STATUSES:
                raise RunStateError(f"run {run_id} is already {status}; no further events accepted")
            event = self._insert_event(
                conn, run_id, event_type, message, payload, agent_id, parent_agent_id, task_id
            )
            new_status = RunStatus.RUNNING if event_type == EventType.RUN_STARTED else status
            conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (new_status.value, event.timestamp.isoformat(), run_id),
            )
            return event

    def get_run(self, run_id: str) -> Run:
        run_id = _run_id(run_id)
        with self._tx() as conn:
            return Run(**self._get_run_row(conn, run_id))

    def list_events(self, run_id: str) -> list[RunEvent]:
        run_id = _run_id(run_id)
        with self._tx() as conn:
            self._get_run_row(conn, run_id)
            rows = conn.execute(
                "SELECT * FROM run_events WHERE run_id = ? ORDER BY timestamp, rowid", (run_id,)
            ).fetchall()
        return [
            RunEvent(**{k: r[k] for k in r.keys() if k != "payload_json"},
                     payload=json.loads(r["payload_json"]) if r["payload_json"] else None)
            for r in rows
        ]

    def finish_run(self, run_id: str, status: str, summary: str | None = None) -> Run:
        run_id = _run_id(run_id)
        status = _enum(RunStatus, "status", status)
        if status not in TERMINAL_STATUSES:
            allowed = ", ".join(s.value for s in TERMINAL_STATUSES)
            raise ValueError(f"finish_run status must be one of: {allowed}")
        summary = _text("summary", summary, optional=True)
        with self._tx() as conn:
            current = RunStatus(self._get_run_row(conn, run_id)["status"])
            if current in TERMINAL_STATUSES:
                raise RunStateError(f"run {run_id} is already {current}")
            event_type = EventType.RUN_COMPLETED if status == RunStatus.COMPLETED else EventType.RUN_FAILED
            event = self._insert_event(conn, run_id, event_type, summary or f"Run {status}")
            conn.execute(
                "UPDATE runs SET status = ?, summary = ?, updated_at = ? WHERE run_id = ?",
                (status.value, summary, event.timestamp.isoformat(), run_id),
            )
            return Run(**self._get_run_row(conn, run_id))
