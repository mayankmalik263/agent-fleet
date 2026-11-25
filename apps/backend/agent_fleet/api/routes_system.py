from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, Any

from fastapi import APIRouter, Body, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select

from ..core.config import REPO_ROOT, get_settings
from ..core.enums import AgentStatus, RunStatus
from ..core.time import utcnow
from ..integrations import graphify
from ..models import Agent, AgentMessage, Run, RunnerDevice, Task
from ..providers.registry import all_providers
from ..schemas import (
    IntegrationStatus,
    Overview,
    ProviderStatus,
    RunnerRead,
    RunnerStatusResponse,
    SystemStatus,
)
from ..services.hooks import record_hook_event
from ..services.queue import ACTIVE_RUN_STATUSES
from .deps import DB, WorkspaceId, WriteDB

router = APIRouter(tags=["system"])


def _version() -> str:
    try:
        return version("agent-fleet")
    except PackageNotFoundError:
        return "dev"


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _providers(refresh: bool) -> list[ProviderStatus]:
    # Detection runs `claude` subprocesses; keep it off the event loop.
    providers = await run_in_threadpool(all_providers, refresh)
    return [ProviderStatus(**p.__dict__) for p in providers]


def runner_status(db: Any, workspace_id: str) -> RunnerStatusResponse:
    settings = get_settings()
    window = timedelta(seconds=max(15.0, settings.runner_poll_seconds * 5))
    now = utcnow()
    devices = list(db.scalars(select(RunnerDevice).where(RunnerDevice.workspace_id == workspace_id)))
    runners = []
    for d in devices:
        item = RunnerRead.model_validate(d)
        item.online = d.status.value != "offline" and d.last_seen_at is not None and now - d.last_seen_at < window
        runners.append(item)
    queued = (
        db.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.workspace_id == workspace_id, Run.status == RunStatus.QUEUED)
        )
        or 0
    )
    active = (
        db.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.workspace_id == workspace_id, Run.status.in_(ACTIVE_RUN_STATUSES))
        )
        or 0
    )
    return RunnerStatusResponse(
        runners=runners, any_online=any(r.online for r in runners), queued_runs=queued, active_runs=active
    )


def _graphify_status() -> IntegrationStatus:
    st = graphify.status(REPO_ROOT)
    return IntegrationStatus(
        name="graphify",
        status="available" if st.installed and st.graph_present else ("installed" if st.installed else "not_installed"),
        message=st.message,
        details={"optional": True, "graph_path": st.graph_path or ""},
    )


@router.get("/api/v1/system/status", response_model=SystemStatus)
async def system_status(db: DB, workspace_id: WorkspaceId, refresh: Annotated[bool, Query()] = False) -> SystemStatus:
    providers = await _providers(refresh)
    runner = runner_status(db, workspace_id)
    settings = get_settings()
    ready = any(p.status.value == "connected" for p in providers) and runner.any_online
    return SystemStatus(
        status="ok" if ready else "degraded",
        version=_version(),
        mode="local",
        database="sqlite" if settings.is_sqlite else "postgresql",
        providers=providers,
        runner=runner,
        integrations=[await run_in_threadpool(_graphify_status)],
    )


@router.get("/api/v1/system/providers", response_model=list[ProviderStatus])
async def system_providers(refresh: Annotated[bool, Query()] = False) -> list[ProviderStatus]:
    return await _providers(refresh)


@router.get("/api/v1/runner/status", response_model=RunnerStatusResponse)
def get_runner_status(db: DB, workspace_id: WorkspaceId) -> RunnerStatusResponse:
    return runner_status(db, workspace_id)


@router.get("/api/v1/overview", response_model=Overview)
def overview(db: DB, workspace_id: WorkspaceId) -> Overview:
    def count(model: Any, *where: Any) -> int:
        return db.scalar(select(func.count()).select_from(model).where(model.workspace_id == workspace_id, *where)) or 0

    by_status = dict(
        db.execute(select(Run.status, func.count()).where(Run.workspace_id == workspace_id).group_by(Run.status)).all()
    )
    latest = db.scalar(select(Run.id).where(Run.workspace_id == workspace_id).order_by(Run.created_at.desc()).limit(1))
    total_events = (
        db.scalar(select(func.coalesce(func.sum(Run.event_seq), 0)).where(Run.workspace_id == workspace_id)) or 0
    )
    return Overview(
        total_runs=count(Run),
        active_runs=count(Run, Run.status.in_(ACTIVE_RUN_STATUSES)),
        total_agents=count(Agent),
        running_agents=count(Agent, Agent.status.in_([AgentStatus.RUNNING, AgentStatus.REVIEWING])),
        total_tasks=count(Task),
        total_messages=count(AgentMessage),
        total_events=int(total_events),
        runs_by_status={k.value if hasattr(k, "value") else str(k): v for k, v in by_status.items()},
        latest_run_id=latest,
    )


@router.post("/api/v1/integrations/claude-code/hooks")
def claude_code_hook(db: WriteDB, workspace_id: WorkspaceId, data: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    result = record_hook_event(db, workspace_id, data)
    db.commit()
    return result
