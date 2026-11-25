"""Enumerations shared by the database, the REST API, the MCP server and the runner."""

from enum import StrEnum


class RunSource(StrEnum):
    DASHBOARD = "dashboard"
    CLAUDE_CODE = "claude_code"
    API = "api"


class ExecutionMode(StrEnum):
    LOCAL_CLAUDE_CODE = "local_claude_code"
    API_PROVIDER = "api_provider"


class ProviderName(StrEnum):
    CLAUDE_CODE_LOCAL = "claude_code_local"
    ANTHROPIC_API = "anthropic_api"


class RunStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStatus(StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionPolicy(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE_EDIT = "workspace_edit"


class MessageType(StrEnum):
    INSTRUCTION = "instruction"
    QUESTION = "question"
    ANSWER = "answer"
    STATUS = "status"
    RESULT = "result"
    REVIEW = "review"
    NOTE = "note"


class EventSource(StrEnum):
    API = "api"
    MCP = "mcp"
    RUNNER = "runner"
    HOOK = "hook"
    SYSTEM = "system"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RunnerStatus(StrEnum):
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"


class ProviderConnectionStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    NOT_CONFIGURED = "not_configured"
    AUTHENTICATION_REQUIRED = "authentication_required"
    UNSUPPORTED_IN_LOCAL_MODE = "unsupported_in_local_mode"


class EventType(StrEnum):
    RUN_CREATED = "run.created"
    RUN_QUEUED = "run.queued"
    RUN_STARTED = "run.started"
    RUN_STATUS_CHANGED = "run.status_changed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"

    AGENT_CREATED = "agent.created"
    AGENT_STARTED = "agent.started"
    AGENT_STATUS_CHANGED = "agent.status_changed"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_WAITING = "agent.waiting"

    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_BLOCKED = "task.blocked"
    TASK_REVIEW_REQUESTED = "task.review_requested"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_STATUS_CHANGED = "task.status_changed"

    MESSAGE_SENT = "message.sent"
    MESSAGE_RECEIVED = "message.received"

    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    RUNNER_CONNECTED = "runner.connected"
    RUNNER_DISCONNECTED = "runner.disconnected"
    EXECUTION_SESSION_STARTED = "execution.session_started"
    EXECUTION_SESSION_ENDED = "execution.session_ended"
    EXECUTION_USAGE_REPORTED = "execution.usage_reported"
    EXECUTION_NOTICE = "execution.notice"

    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"


# Event types that agents may append directly with append_run_event. Lifecycle and state events are
# written only by the service that changes the state, so the event log and the tables always agree.
FREEFORM_EVENT_TYPES = frozenset(
    {
        EventType.AGENT_WAITING,
        EventType.TASK_PROGRESS,
        EventType.MESSAGE_RECEIVED,
        EventType.TOOL_STARTED,
        EventType.TOOL_COMPLETED,
        EventType.TOOL_FAILED,
        EventType.EXECUTION_NOTICE,
    }
)
