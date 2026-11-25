"""Database-backed job queue for the local runner: registration, safe claiming, leases and recovery.

Claiming is one conditional UPDATE (status must still be 'queued'), so two runners can never take
the same run. A claim holds a lease; the runner renews it while the Claude Code process lives.
An expired lease means the runner died: the run is re-queued if no session started yet, else failed.
"""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.enums import AgentStatus, EventSource, EventType, RunnerStatus, RunSource, RunStatus
from ..core.state_machine import RUN_TERMINAL
from ..core.time import utcnow
from ..models import Run, RunnerDevice
from .events import EventService
from .runs import RunService

ACTIVE_RUN_STATUSES = (RunStatus.PLANNING, RunStatus.RUNNING, RunStatus.AWAITING_APPROVAL)


class RunQueue:
    def __init__(self, session: Session, workspace_id: str):
        self.session = session
        self.workspace_id = workspace_id
        self.events = EventService(session)
        self.settings = get_settings()

    # ---------- runner registry ----------
    def register_runner(self, name: str, runtime_type: str, details: dict | None = None) -> RunnerDevice:
        device = self.session.scalars(
            select(RunnerDevice).where(RunnerDevice.workspace_id == self.workspace_id, RunnerDevice.name == name)
        ).one_or_none()
        if device is None:
            device = RunnerDevice(
                workspace_id=self.workspace_id, name=name, runtime_type=runtime_type, status=RunnerStatus.ONLINE
            )
            self.session.add(device)
        device.runtime_type = runtime_type
        device.status = RunnerStatus.ONLINE
        device.last_seen_at = utcnow()
        device.details_json = details
        self.session.flush()
        return device

    def heartbeat(self, runner_id: str, busy: bool, details: dict | None = None) -> None:
        device = self.session.get(RunnerDevice, runner_id)
        if device is None:
            return
        device.status = RunnerStatus.BUSY if busy else RunnerStatus.ONLINE
        device.last_seen_at = utcnow()
        if details is not None:
            device.details_json = details

    def mark_offline(self, runner_id: str) -> None:
        device = self.session.get(RunnerDevice, runner_id)
        if device is not None:
            device.status = RunnerStatus.OFFLINE
            device.last_seen_at = utcnow()

    # ---------- claiming ----------
    def claim_next(self, runner_id: str) -> Run | None:
        now = utcnow()
        candidate = self.session.scalar(
            select(Run.id)
            .where(
                Run.workspace_id == self.workspace_id,
                Run.status == RunStatus.QUEUED,
                Run.source != RunSource.CLAUDE_CODE,
                Run.attempt_count < self.settings.run_max_attempts,
            )
            .order_by(Run.created_at)
            .limit(1)
        )
        if candidate is None:
            return None
        claimed = self.session.execute(
            update(Run)
            .where(Run.id == candidate, Run.status == RunStatus.QUEUED)
            .values(
                status=RunStatus.PLANNING,
                runner_device_id=runner_id,
                claimed_at=now,
                lease_expires_at=now + timedelta(seconds=self.settings.runner_lease_seconds),
                attempt_count=Run.attempt_count + 1,
                started_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            return None
        run = self.session.get(Run, candidate, populate_existing=True)
        assert run is not None
        device = self.session.get(RunnerDevice, runner_id)
        self.events.emit(
            run,
            EventType.RUNNER_CONNECTED,
            f"Runner {device.name if device else runner_id} claimed the run",
            source=EventSource.RUNNER,
            payload={"runner_id": runner_id, "attempt": run.attempt_count},
        )
        self.events.emit(
            run,
            EventType.RUN_STATUS_CHANGED,
            "Run is planning",
            source=EventSource.RUNNER,
            payload={"from": RunStatus.QUEUED.value, "to": RunStatus.PLANNING.value},
        )
        return run

    def renew_lease(self, run_id: str, runner_id: str) -> bool:
        """Extend the lease. Returns False only when the process must stop: the run was cancelled, or it
        is no longer ours. A run that the orchestrator already completed or failed keeps going, so Claude
        Code can end normally and report its final result and usage."""
        run = self.session.get(Run, run_id, populate_existing=True)
        if run is None or run.runner_device_id != runner_id:
            return False
        if run.cancel_requested or run.status == RunStatus.CANCELLED:
            return False
        if run.status not in RUN_TERMINAL:
            run.lease_expires_at = utcnow() + timedelta(seconds=self.settings.runner_lease_seconds)
        return True

    def release(self, run: Run, runner_id: str, reason: str) -> None:
        """Give back a claim that never started a Claude Code session (for example a start-up error)."""
        if (
            run.status == RunStatus.PLANNING
            and run.session_id is None
            and run.attempt_count < self.settings.run_max_attempts
        ):
            run.runner_device_id = None
            run.lease_expires_at = None
            RunService(self.session, self.workspace_id, EventSource.RUNNER).transition(
                run, RunStatus.QUEUED, f"Run returned to the queue: {reason}"
            )
        self.events.emit(
            run,
            EventType.RUNNER_DISCONNECTED,
            "Runner released the run",
            source=EventSource.RUNNER,
            payload={"runner_id": runner_id, "reason": reason},
        )

    def recover(self, skip_run_ids: set[str] | None = None) -> list[str]:
        """Fix runs left behind by a crashed runner. Returns the ids it changed.
        A run is recovered only when its lease expired AND its runner has not sent a heartbeat for a
        whole lease period, so a runner that was only paused (for example by sleep) keeps its run."""
        now = utcnow()
        skip = skip_run_ids or set()
        stale_before = now - timedelta(seconds=self.settings.runner_lease_seconds)
        changed: list[str] = []
        service = RunService(self.session, self.workspace_id, EventSource.SYSTEM)
        expired = self.session.scalars(
            select(Run).where(
                Run.workspace_id == self.workspace_id,
                Run.status.in_(ACTIVE_RUN_STATUSES),
                Run.lease_expires_at.is_not(None),
                Run.lease_expires_at < now,
            )
        ).all()
        for run in expired:
            if run.id in skip:
                continue
            device = self.session.get(RunnerDevice, run.runner_device_id) if run.runner_device_id else None
            if device is not None and device.last_seen_at is not None and device.last_seen_at > stale_before:
                continue
            if (
                run.status == RunStatus.PLANNING
                and run.session_id is None
                and run.attempt_count < self.settings.run_max_attempts
            ):
                run.runner_device_id = None
                run.lease_expires_at = None
                service.transition(run, RunStatus.QUEUED, "Runner lease expired before the session started; re-queued")
            else:
                run.error_message = "The runner stopped before the run finished (lease expired)."
                service.transition(run, RunStatus.FAILED, run.error_message)
                service.close_agents(run, AgentStatus.CANCELLED, "stopped because the runner was lost")
                service.close_tasks(run, "stopped because the runner was lost")
            changed.append(run.id)
        exhausted = self.session.scalars(
            select(Run).where(
                Run.workspace_id == self.workspace_id,
                Run.status == RunStatus.QUEUED,
                Run.attempt_count >= self.settings.run_max_attempts,
            )
        ).all()
        for run in exhausted:
            run.error_message = f"Run gave up after {run.attempt_count} attempts."
            service.transition(run, RunStatus.FAILED, run.error_message)
            changed.append(run.id)
        return changed
