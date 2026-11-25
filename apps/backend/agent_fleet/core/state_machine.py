"""Allowed status transitions for runs, agents and tasks."""

from .enums import AgentStatus, RunStatus, TaskStatus
from .errors import InvalidTransitionError

RUN_TERMINAL = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED})
AGENT_TERMINAL = frozenset({AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED})
TASK_TERMINAL = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED})
AGENT_ACTIVE = frozenset({AgentStatus.RUNNING, AgentStatus.REVIEWING})

_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.PLANNING, RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED}),
    # PLANNING -> QUEUED is used only by the runner to give back a claim that never started a session.
    RunStatus.PLANNING: frozenset(
        {
            RunStatus.QUEUED,
            RunStatus.RUNNING,
            RunStatus.AWAITING_APPROVAL,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.RUNNING: frozenset(
        {RunStatus.AWAITING_APPROVAL, RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.AWAITING_APPROVAL: frozenset({RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED}),
}


def check_run_transition(current: RunStatus, target: RunStatus) -> None:
    if target not in _RUN_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransitionError(
            f"run cannot move from {current} to {target}",
            details={"current": current.value, "target": target.value},
        )


def check_agent_transition(current: AgentStatus, target: AgentStatus) -> None:
    # Non-terminal agents may move to any status; terminal agents are final.
    if current in AGENT_TERMINAL and current != target:
        raise InvalidTransitionError(
            f"agent is already {current}", details={"current": current.value, "target": target.value}
        )


def check_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    if current in TASK_TERMINAL and current != target:
        raise InvalidTransitionError(
            f"task is already {current}", details={"current": current.value, "target": target.value}
        )
