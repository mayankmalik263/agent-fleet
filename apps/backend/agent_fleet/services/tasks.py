"""Task delegation records: creation, status, progress and results."""

from typing import Any

from sqlalchemy.orm import Session

from ..core.enums import EventSource, EventType, TaskPriority, TaskStatus
from ..core.errors import InvalidTransitionError, ValidationFailedError
from ..core.redaction import redact_text, sanitize
from ..core.state_machine import TASK_TERMINAL, check_task_transition
from ..core.time import utcnow
from ..models import Agent, Task
from ..repositories import scoped
from .agents import ensure_run_open
from .events import EventService
from .runs import MAX_DESCRIPTION, MAX_TITLE, _clean_text

_STATUS_EVENTS = {
    TaskStatus.BLOCKED: EventType.TASK_BLOCKED,
    TaskStatus.REVIEW: EventType.TASK_REVIEW_REQUESTED,
    TaskStatus.COMPLETED: EventType.TASK_COMPLETED,
    TaskStatus.FAILED: EventType.TASK_FAILED,
}


def _parse(enum_cls: Any, value: Any, field: str) -> Any:
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in enum_cls)
        raise ValidationFailedError(
            f"invalid {field} {value!r}; expected one of: {allowed}", details={"field": field}
        ) from None


def _check_progress(progress: int | None) -> int | None:
    if progress is None:
        return None
    if isinstance(progress, bool) or not isinstance(progress, int) or not 0 <= progress <= 100:
        raise ValidationFailedError(
            "progress_percentage must be an integer from 0 to 100", details={"field": "progress_percentage"}
        )
    return progress


class TaskService:
    def __init__(self, session: Session, workspace_id: str, source: EventSource):
        self.session = session
        self.workspace_id = workspace_id
        self.source = source
        self.events = EventService(session)

    def create(
        self,
        run_id: str,
        title: str,
        description: str,
        assigned_agent_id: str,
        *,
        created_by_agent_id: str | None = None,
        parent_task_id: str | None = None,
        priority: TaskPriority | str = TaskPriority.NORMAL,
    ) -> Task:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        ensure_run_open(run)
        title_clean = _clean_text(title, "title", MAX_TITLE)
        description_clean = _clean_text(description, "description", MAX_DESCRIPTION)
        assignee = scoped.get_agent(self.session, self.workspace_id, assigned_agent_id, run.id)
        creator: Agent | None = None
        if scoped.optional_id(created_by_agent_id, "created_by_agent_id"):
            creator = scoped.get_agent(self.session, self.workspace_id, created_by_agent_id or "", run.id)
        elif assignee.parent_agent_id:
            creator = self.session.get(Agent, assignee.parent_agent_id)
        parent_task = None
        if scoped.optional_id(parent_task_id, "parent_task_id"):
            parent_task = scoped.get_task(self.session, self.workspace_id, parent_task_id or "", run.id)

        task = Task(
            workspace_id=self.workspace_id,
            run_id=run.id,
            title=title_clean or "",
            description=redact_text(description_clean or "", MAX_DESCRIPTION),
            assigned_agent_id=assignee.id,
            created_by_agent_id=creator.id if creator else None,
            parent_task_id=parent_task.id if parent_task else None,
            priority=_parse(TaskPriority, priority, "priority"),
            status=TaskStatus.PENDING,
        )
        self.session.add(task)
        self.session.flush()
        self.events.emit(
            run,
            EventType.TASK_CREATED,
            f"Task '{task.title}' delegated to {assignee.name}" + (f" by {creator.name}" if creator else ""),
            source=self.source,
            agent_id=creator.id if creator else None,
            parent_agent_id=None,
            task_id=task.id,
            payload={
                "assigned_agent_id": assignee.id,
                "created_by_agent_id": task.created_by_agent_id,
                "priority": task.priority.value,
                "parent_task_id": task.parent_task_id,
            },
        )
        return task

    def update_status(
        self,
        run_id: str,
        task_id: str,
        status: TaskStatus | str | None = None,
        progress_percentage: int | None = None,
        *,
        actor_agent_id: str | None = None,
        error_message: str | None = None,
    ) -> Task:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        task = scoped.get_task(self.session, self.workspace_id, task_id, run.id)
        progress = _check_progress(progress_percentage)
        target = _parse(TaskStatus, status, "status") if status is not None else task.status
        if status is None and progress is None:
            raise ValidationFailedError("give a status, a progress_percentage, or both")
        check_task_transition(task.status, target)
        if target != task.status or progress is not None:
            ensure_run_open(run)
        actor = actor_agent_id or task.assigned_agent_id

        previous = task.status
        now = utcnow()
        status_changed = target != previous
        task.status = target
        if progress is not None:
            task.progress_percentage = progress
        if error_message:
            task.error_message = redact_text(error_message, 4_000)
        assignee = self.session.get(Agent, task.assigned_agent_id) if task.assigned_agent_id else None
        etype = EventType.TASK_PROGRESS
        if status_changed:
            etype = _STATUS_EVENTS.get(target, EventType.TASK_STATUS_CHANGED)
            if target == TaskStatus.IN_PROGRESS and task.started_at is None:
                task.started_at = now
                etype = EventType.TASK_STARTED
            if target in TASK_TERMINAL:
                task.completed_at = now
            if assignee is not None:
                if target == TaskStatus.IN_PROGRESS:
                    assignee.current_task_id = task.id
                elif target in TASK_TERMINAL and assignee.current_task_id == task.id:
                    assignee.current_task_id = None
        elif progress is None:
            return task
        text = (
            f"Task '{task.title}': {previous.value} -> {target.value}"
            if status_changed
            else f"Task '{task.title}' progress {progress}%"
        )
        self.events.emit(
            run,
            etype,
            text,
            source=self.source,
            agent_id=actor,
            task_id=task.id,
            payload={"from": previous.value, "to": target.value, "progress_percentage": task.progress_percentage},
        )
        return task

    def submit_result(
        self,
        run_id: str,
        task_id: str,
        agent_id: str,
        result_summary: str,
        result_payload: dict[str, Any] | None = None,
    ) -> Task:
        run = scoped.get_run(self.session, self.workspace_id, run_id)
        ensure_run_open(run)
        task = scoped.get_task(self.session, self.workspace_id, task_id, run.id)
        agent = scoped.get_agent(self.session, self.workspace_id, agent_id, run.id)
        allowed = {task.assigned_agent_id, task.created_by_agent_id, run.root_agent_id}
        if agent.id not in allowed:
            raise ValidationFailedError(
                "only the assigned agent, the delegating agent or the root orchestrator can submit this result",
                details={"agent_id": agent.id},
            )
        if task.status in TASK_TERMINAL and task.status != TaskStatus.COMPLETED:
            raise InvalidTransitionError(
                f"task is already {task.status}; it cannot receive a result", details={"current": task.status.value}
            )
        summary = _clean_text(result_summary, "result_summary", MAX_DESCRIPTION)
        if result_payload is not None and not isinstance(result_payload, dict):
            raise ValidationFailedError("result_payload must be a JSON object")
        task.result_summary = redact_text(summary or "", MAX_DESCRIPTION)
        task.result_payload = sanitize(result_payload) if result_payload else None
        if task.status not in TASK_TERMINAL:
            check_task_transition(task.status, TaskStatus.COMPLETED)
            now = utcnow()
            task.status = TaskStatus.COMPLETED
            task.completed_at = now
            task.started_at = task.started_at or now
            task.progress_percentage = 100
            assignee = self.session.get(Agent, task.assigned_agent_id) if task.assigned_agent_id else None
            if assignee is not None and assignee.current_task_id == task.id:
                assignee.current_task_id = None
        self.events.emit(
            run,
            EventType.TASK_COMPLETED,
            f"Result submitted for '{task.title}' by {agent.name}",
            source=self.source,
            agent_id=agent.id,
            task_id=task.id,
            payload={
                "result_preview": task.result_summary[:500] if task.result_summary else "",
                "has_payload": bool(result_payload),
            },
        )
        return task
