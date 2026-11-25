from fastapi import APIRouter

from ..core.enums import EventSource
from ..models import Agent, Task
from ..repositories import scoped
from ..schemas import AgentDetails, AgentRead, AgentUpdate, TaskRead, TaskUpdate
from ..services.agents import AgentService
from ..services.tasks import TaskService
from .deps import DB, WorkspaceId, WriteDB

router = APIRouter(prefix="/api/v1", tags=["agents", "tasks"])


@router.get("/agents/{agent_id}", response_model=AgentDetails)
def get_agent(agent_id: str, db: DB, workspace_id: WorkspaceId) -> dict:
    agent = scoped.get_agent(db, workspace_id, agent_id)
    return AgentService(db, workspace_id, EventSource.API).details(agent.run_id, agent.id)


@router.patch("/agents/{agent_id}", response_model=AgentRead)
def update_agent(agent_id: str, body: AgentUpdate, db: WriteDB, workspace_id: WorkspaceId) -> Agent:
    agent = scoped.get_agent(db, workspace_id, agent_id)
    updated = AgentService(db, workspace_id, EventSource.API).update_status(agent.run_id, agent.id, body.status)
    db.commit()
    return updated


@router.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: str, db: DB, workspace_id: WorkspaceId) -> Task:
    return scoped.get_task(db, workspace_id, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(task_id: str, body: TaskUpdate, db: WriteDB, workspace_id: WorkspaceId) -> Task:
    task = scoped.get_task(db, workspace_id, task_id)
    updated = TaskService(db, workspace_id, EventSource.API).update_status(
        task.run_id, task.id, body.status, body.progress_percentage
    )
    db.commit()
    return updated
