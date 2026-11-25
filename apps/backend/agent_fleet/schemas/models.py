"""Pydantic response and request schemas for the REST API (and reused by the MCP tools)."""

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from ..core.enums import (
    AgentStatus,
    ApprovalStatus,
    EventSource,
    ExecutionMode,
    MessageType,
    PermissionPolicy,
    ProviderConnectionStatus,
    ProviderName,
    RunnerStatus,
    RunSource,
    RunStatus,
    TaskPriority,
    TaskStatus,
)

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


# ---------- runs ----------
class RunCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    task_description: str = Field(min_length=1, max_length=20_000)
    execution_provider: ProviderName = ProviderName.CLAUDE_CODE_LOCAL
    workspace_path: str | None = Field(default=None, max_length=1_000)
    orchestrator_model: Literal["sonnet", "haiku"] = "sonnet"
    permission_policy: PermissionPolicy = PermissionPolicy.READ_ONLY
    max_concurrent_agents: int | None = Field(
        default=None, ge=1, le=20, description="Default: AGENT_FLEET_MAX_CONCURRENT_AGENTS"
    )
    confirm_workspace_edit: bool = False


class RunRead(ORM):
    id: str
    workspace_id: str
    title: str
    task_description: str
    source: RunSource
    execution_mode: ExecutionMode
    provider: ProviderName
    root_agent_id: str | None
    status: RunStatus
    workspace_path: str | None
    permission_policy: PermissionPolicy
    orchestrator_model: str
    max_concurrent_agents: int
    session_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    final_summary: str | None
    error_message: str | None
    attempt_count: int
    cancel_requested: bool
    usage_json: dict[str, Any] | None
    event_count: int


class RunListItem(RunRead):
    agent_count: int = 0
    task_count: int = 0
    message_count: int = 0


# ---------- agents ----------
class AgentRead(ORM):
    id: str
    run_id: str
    name: str
    role: str
    model_alias: str
    provider: str
    parent_agent_id: str | None
    status: AgentStatus
    current_task_id: str | None
    external_ref: str | None
    input_tokens: int | None
    output_tokens: int | None
    tool_call_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class AgentUpdate(BaseModel):
    status: AgentStatus


# ---------- tasks ----------
class TaskRead(ORM):
    id: str
    run_id: str
    title: str
    description: str
    assigned_agent_id: str | None
    created_by_agent_id: str | None
    parent_task_id: str | None
    priority: TaskPriority
    status: TaskStatus
    progress_percentage: int | None
    result_summary: str | None
    result_payload: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    progress_percentage: int | None = Field(default=None, ge=0, le=100)


# ---------- messages and events ----------
class MessageRead(ORM):
    id: str
    run_id: str
    sender_agent_id: str | None
    receiver_agent_id: str | None
    task_id: str | None
    message_type: MessageType
    content: str
    metadata_json: dict[str, Any] | None
    timestamp: datetime


class EventRead(ORM):
    id: str
    run_id: str
    sequence_number: int
    event_type: str
    agent_id: str | None
    parent_agent_id: str | None
    task_id: str | None
    timestamp: datetime
    message: str
    payload: dict[str, Any] | None = None
    source: EventSource


class ApprovalRead(ORM):
    id: str
    run_id: str
    requested_by_agent_id: str | None
    action_type: str
    description: str
    status: ApprovalStatus
    created_at: datetime
    resolved_at: datetime | None


class HierarchyNode(BaseModel):
    agent_id: str
    name: str
    children: list["HierarchyNode"] = Field(default_factory=list)


class RunSnapshot(BaseModel):
    run: RunRead
    agents: list[AgentRead]
    hierarchy: list[HierarchyNode]
    tasks: list[TaskRead]
    recent_messages: list[MessageRead]
    event_counts: dict[str, int]
    total_events: int
    agent_status_counts: dict[str, int]
    task_status_counts: dict[str, int]


class AgentDetails(BaseModel):
    agent: AgentRead
    parent: AgentRead | None
    current_task: TaskRead | None
    children: list[AgentRead]
    recent_messages: list[MessageRead]
    tool_events: list[EventRead]
    tasks: list[TaskRead]


# ---------- system ----------
class ProviderStatus(BaseModel):
    provider: str
    label: str
    status: ProviderConnectionStatus
    message: str
    local_mode_supported: bool
    details: dict[str, Any] = Field(default_factory=dict)


class RunnerRead(ORM):
    id: str
    name: str
    runtime_type: str
    status: RunnerStatus
    last_seen_at: datetime | None
    details_json: dict[str, Any] | None
    online: bool = False


class RunnerStatusResponse(BaseModel):
    runners: list[RunnerRead]
    any_online: bool
    queued_runs: int
    active_runs: int


class IntegrationStatus(BaseModel):
    name: str
    status: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class SystemStatus(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    mode: Literal["local"]
    database: str
    providers: list[ProviderStatus]
    runner: RunnerStatusResponse
    integrations: list[IntegrationStatus]


class Overview(BaseModel):
    total_runs: int
    active_runs: int
    total_agents: int
    running_agents: int
    total_tasks: int
    total_messages: int
    total_events: int
    runs_by_status: dict[str, int]
    latest_run_id: str | None
