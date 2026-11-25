"""Domain types shared by the store and the MCP layer."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class Source(StrEnum):
    CLAUDE_CODE = "claude_code"
    DASHBOARD = "dashboard"
    API = "api"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED})


class EventType(StrEnum):
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    MESSAGE_SENT = "message.sent"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


# Lifecycle events owned by create_run / finish_run, so status and event log can't disagree.
LIFECYCLE_EVENTS = frozenset({EventType.RUN_CREATED, EventType.RUN_COMPLETED, EventType.RUN_FAILED})


class Run(BaseModel):
    run_id: str
    task: str
    source: Source
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    summary: str | None = None


class RunEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: EventType
    agent_id: str | None = None
    parent_agent_id: str | None = None
    task_id: str | None = None
    message: str
    payload: dict[str, Any] | None = None
    timestamp: datetime
