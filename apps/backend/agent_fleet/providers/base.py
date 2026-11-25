"""Provider and runtime interfaces. The orchestration core depends on these, not on Claude Code.

- ModelProvider: a source of model execution (local Claude Code today, BYOK API later).
- ProviderHealthCheck: reports whether the provider can run work right now.
- ExecutionRuntime: runs one whole orchestration session for a run and streams structured messages.
- AgentExecutor: runs one agent task (for API-style providers that execute agents one by one).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..core.enums import PermissionPolicy, ProviderConnectionStatus


@dataclass
class ProviderHealth:
    provider: str
    label: str
    status: ProviderConnectionStatus
    message: str
    local_mode_supported: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRequest:
    run_id: str
    workspace_id: str
    prompt: str
    cwd: Path
    model: str
    permission_policy: PermissionPolicy
    mcp_config_path: Path
    agents_path: Path
    timeout_seconds: int
    max_concurrent_agents: int
    web_access: bool = False


@dataclass
class ExecutionOutcome:
    exit_code: int | None
    success: bool
    session_id: str | None = None
    result_text: str | None = None
    error: str | None = None
    timed_out: bool = False
    cancelled: bool = False
    usage: dict[str, Any] | None = None


# Called for every parsed stream message; return value is ignored. Must not raise for bad input.
MessageSink = Callable[[dict[str, Any]], Awaitable[None]]
# Polled by the runtime; returns False when the run must stop (cancelled or lease lost).
KeepGoing = Callable[[], Awaitable[bool]]


class ProviderHealthCheck(Protocol):
    def check(self, *, refresh: bool = False) -> ProviderHealth: ...


class ExecutionRuntime(Protocol):
    name: str

    async def execute(
        self, request: ExecutionRequest, on_message: MessageSink, keep_going: KeepGoing
    ) -> ExecutionOutcome: ...


class AgentExecutor(Protocol):
    async def run_agent_task(
        self, *, run_id: str, agent_id: str, task_id: str, model: str, instructions: str
    ) -> dict[str, Any]: ...


class ModelProvider(Protocol):
    name: str
    label: str
    model_aliases: tuple[str, ...]

    def health(self, *, refresh: bool = False) -> ProviderHealth: ...

    def runtime(self) -> ExecutionRuntime: ...
