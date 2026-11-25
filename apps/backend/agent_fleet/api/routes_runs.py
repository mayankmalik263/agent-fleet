from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from ..core.enums import EventSource, RunSource, RunStatus, TaskStatus
from ..models import Agent, AgentMessage, ApprovalRequest, Run, RunEvent, Task
from ..repositories import scoped
from ..schemas import (
    AgentRead,
    ApprovalRead,
    EventRead,
    MessageRead,
    Page,
    RunCreate,
    RunListItem,
    RunRead,
    RunSnapshot,
    TaskRead,
)
from ..services.runs import NewRun, RunService
from .deps import DB, WorkspaceId, WriteDB
from .pagination import Limit, Offset, apply_sort, paginate

router = APIRouter(prefix="/api/v1", tags=["runs"])


@router.post("/runs", response_model=RunRead, status_code=status.HTTP_201_CREATED)
def create_run(body: RunCreate, db: WriteDB, workspace_id: WorkspaceId) -> Run:
    run = RunService(db, workspace_id, EventSource.API).create(
        NewRun(
            task_description=body.task_description,
            title=body.title,
            source=RunSource.DASHBOARD,
            provider=body.execution_provider,
            workspace_path=body.workspace_path,
            orchestrator_model=body.orchestrator_model,
            permission_policy=body.permission_policy,
            max_concurrent_agents=body.max_concurrent_agents,
            confirm_workspace_edit=body.confirm_workspace_edit,
        )
    )
    db.commit()
    return run


@router.get("/runs", response_model=Page[RunListItem])
def list_runs(
    db: DB,
    workspace_id: WorkspaceId,
    limit: Limit = 50,
    offset: Offset = 0,
    status_filter: Annotated[list[RunStatus] | None, Query(alias="status")] = None,
    source: Annotated[RunSource | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    sort: Annotated[str | None, Query()] = "-created_at",
) -> dict:
    stmt = select(Run).where(Run.workspace_id == workspace_id)
    if status_filter:
        stmt = stmt.where(Run.status.in_(status_filter))
    if source:
        stmt = stmt.where(Run.source == source)
    if search:
        stmt = stmt.where(Run.title.ilike(f"%{search}%"))
    stmt = apply_sort(
        stmt,
        sort,
        {"created_at": Run.created_at, "updated_at": Run.updated_at, "title": Run.title, "status": Run.status},
        Run.created_at.desc(),
    )
    runs, total = paginate(db, stmt, limit, offset)
    ids = [r.id for r in runs]

    def counts(model: Any) -> dict[str, int]:
        if not ids:
            return {}
        return dict(
            db.execute(select(model.run_id, func.count()).where(model.run_id.in_(ids)).group_by(model.run_id)).all()
        )

    agents, tasks, messages = counts(Agent), counts(Task), counts(AgentMessage)
    items = [
        RunListItem.model_validate(r).model_copy(
            update={
                "agent_count": agents.get(r.id, 0),
                "task_count": tasks.get(r.id, 0),
                "message_count": messages.get(r.id, 0),
            }
        )
        for r in runs
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: str, db: DB, workspace_id: WorkspaceId) -> Run:
    return scoped.get_run(db, workspace_id, run_id)


@router.post("/runs/{run_id}/cancel", response_model=RunRead)
def cancel_run(run_id: str, db: WriteDB, workspace_id: WorkspaceId) -> Run:
    run = RunService(db, workspace_id, EventSource.API).cancel(run_id)
    db.commit()
    return run


@router.get("/runs/{run_id}/snapshot", response_model=RunSnapshot)
def run_snapshot(run_id: str, db: DB, workspace_id: WorkspaceId) -> dict:
    return RunService(db, workspace_id, EventSource.API).snapshot(run_id)


@router.get("/runs/{run_id}/events", response_model=Page[EventRead])
def list_events(
    run_id: str,
    db: DB,
    workspace_id: WorkspaceId,
    limit: Limit = 500,
    offset: Offset = 0,
    after: Annotated[int, Query(ge=0, description="Return events with sequence_number greater than this")] = 0,
    event_type: Annotated[list[str] | None, Query()] = None,
    agent_id: Annotated[str | None, Query()] = None,
) -> dict:
    run = scoped.get_run(db, workspace_id, run_id)
    stmt = select(RunEvent).where(RunEvent.run_id == run.id, RunEvent.sequence_number > after)
    if event_type:
        stmt = stmt.where(RunEvent.event_type.in_(event_type))
    if agent_id:
        stmt = stmt.where(RunEvent.agent_id == scoped.parse_id(agent_id, "agent_id"))
    events, total = paginate(db, stmt.order_by(RunEvent.sequence_number), limit, offset)
    return {"items": events, "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}/agents", response_model=list[AgentRead])
def list_agents(run_id: str, db: DB, workspace_id: WorkspaceId) -> list[Agent]:
    run = scoped.get_run(db, workspace_id, run_id)
    return list(db.scalars(select(Agent).where(Agent.run_id == run.id).order_by(Agent.created_at)))


@router.get("/runs/{run_id}/tasks", response_model=list[TaskRead])
def list_tasks(
    run_id: str,
    db: DB,
    workspace_id: WorkspaceId,
    status_filter: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
) -> list[Task]:
    run = scoped.get_run(db, workspace_id, run_id)
    stmt = select(Task).where(Task.run_id == run.id)
    if status_filter:
        stmt = stmt.where(Task.status.in_(status_filter))
    return list(db.scalars(stmt.order_by(Task.created_at)))


@router.get("/runs/{run_id}/messages", response_model=Page[MessageRead])
def list_messages(
    run_id: str,
    db: DB,
    workspace_id: WorkspaceId,
    limit: Limit = 200,
    offset: Offset = 0,
    agent_id: Annotated[str | None, Query()] = None,
) -> dict:
    run = scoped.get_run(db, workspace_id, run_id)
    stmt = select(AgentMessage).where(AgentMessage.run_id == run.id)
    if agent_id:
        aid = scoped.parse_id(agent_id, "agent_id")
        stmt = stmt.where((AgentMessage.sender_agent_id == aid) | (AgentMessage.receiver_agent_id == aid))
    items, total = paginate(db, stmt.order_by(AgentMessage.timestamp), limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}/approvals", response_model=list[ApprovalRead])
def list_approvals(run_id: str, db: DB, workspace_id: WorkspaceId) -> list[ApprovalRequest]:
    run = scoped.get_run(db, workspace_id, run_id)
    return list(
        db.scalars(select(ApprovalRequest).where(ApprovalRequest.run_id == run.id).order_by(ApprovalRequest.created_at))
    )
