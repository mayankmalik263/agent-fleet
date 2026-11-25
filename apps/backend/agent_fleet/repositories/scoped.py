"""Workspace-scoped lookups. Every read goes through these helpers, so a record from another
workspace is reported as "not found" and never leaks across workspaces."""

import uuid
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import NotFoundError, ValidationFailedError
from ..models import Agent, AgentMessage, Run, RunEvent, Task, Workspace

T = TypeVar("T", Run, Agent, Task, AgentMessage, RunEvent)


def parse_id(value: str | None, field: str) -> str:
    if value is None or not str(value).strip():
        raise ValidationFailedError(f"{field} is required", details={"field": field})
    try:
        return str(uuid.UUID(str(value).strip()))
    except ValueError:
        raise ValidationFailedError(f"{field} is not a valid UUID", details={"field": field}) from None


def optional_id(value: str | None, field: str) -> str | None:
    return None if value is None or not str(value).strip() else parse_id(value, field)


def get_workspace(session: Session, workspace_id: str) -> Workspace:
    ws = session.get(Workspace, parse_id(workspace_id, "workspace_id"))
    if ws is None:
        raise NotFoundError("workspace not found", details={"workspace_id": workspace_id})
    return ws


def _get(session: Session, model: type[T], record_id: str, workspace_id: str, field: str) -> T:
    record = session.get(model, parse_id(record_id, field))
    if record is None or record.workspace_id != workspace_id:
        raise NotFoundError(f"{model.__tablename__[:-1].replace('_', ' ')} not found", details={field: record_id})
    return record


def get_run(session: Session, workspace_id: str, run_id: str) -> Run:
    return _get(session, Run, run_id, workspace_id, "run_id")


def get_agent(session: Session, workspace_id: str, agent_id: str, run_id: str | None = None) -> Agent:
    agent = _get(session, Agent, agent_id, workspace_id, "agent_id")
    if run_id is not None and agent.run_id != run_id:
        raise NotFoundError("agent not found in this run", details={"agent_id": agent_id, "run_id": run_id})
    return agent


def get_task(session: Session, workspace_id: str, task_id: str, run_id: str | None = None) -> Task:
    task = _get(session, Task, task_id, workspace_id, "task_id")
    if run_id is not None and task.run_id != run_id:
        raise NotFoundError("task not found in this run", details={"task_id": task_id, "run_id": run_id})
    return task


def agent_by_external_ref(session: Session, run_id: str, external_ref: str) -> Agent | None:
    return session.scalars(
        select(Agent).where(Agent.run_id == run_id, Agent.external_ref == external_ref)
    ).one_or_none()
