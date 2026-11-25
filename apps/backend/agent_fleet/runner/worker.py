"""The local execution runner: polls the database queue, claims runs, runs Claude Code, records events.

It runs as its own process (agent-fleet-runner), separate from the API request lifecycle.
"""

import asyncio
import json
import logging
import socket
import sys
import time
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from ..core.config import Settings, get_settings
from ..core.enums import AgentStatus, EventSource, EventType, RunStatus
from ..core.redaction import redact_text
from ..core.state_machine import RUN_TERMINAL
from ..database import session_scope
from ..models import LOCAL_WORKSPACE_ID, Run
from ..providers.base import ExecutionOutcome, ExecutionRequest
from ..providers.claude_cli import ClaudeInstallation, cached_detect
from ..providers.claude_code import ClaudeCodeLocalRuntime
from ..services.agents import AgentService
from ..services.events import EventService
from ..services.queue import RunQueue
from ..services.runs import MAX_DESCRIPTION, RunService
from .agent_defs import agents_json, load_definitions
from .event_mapper import AUTH_ERRORS, StreamMapper
from .policy import MCP_SERVER_NAME
from .prompt import build_prompt

log = logging.getLogger("agent_fleet.runner")

RECOVER_EVERY = 10.0


def explain_failure(outcome: ExecutionOutcome, api_errors: list[str]) -> str:
    """A user-facing reason. Known Claude API error categories get a clear explanation."""
    if any(e in AUTH_ERRORS for e in api_errors):
        return "Claude Code is not signed in or the account cannot be used. Run `claude auth login`."
    if "rate_limit" in api_errors:
        return "Claude usage or rate limit reached. Wait for the limit to reset, then start a new run."
    if "model_not_found" in api_errors:
        return "The selected model is not available for this Claude account."
    if "billing_error" in api_errors:
        return "Claude reported a billing problem for this account."
    return outcome.error or "Claude Code did not finish successfully."


class Runner:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        factory: sessionmaker[Session] | None = None,
        claude_command: list[str] | None = None,
        detector: Callable[[], ClaudeInstallation] | None = None,
        workspace_id: str = LOCAL_WORKSPACE_ID,
        python_executable: str | None = None,
    ):
        self.settings = settings or get_settings()
        self.factory = factory
        self.claude_command = claude_command
        self.detector = detector or (lambda: cached_detect(refresh=True))
        self.workspace_id = workspace_id
        self.python = python_executable or sys.executable
        self.runner_id: str | None = None
        self.name = f"{self.settings.runner_name}@{socket.gethostname()}"
        self.active: dict[str, asyncio.Task[None]] = {}
        self._stopping = False

    # ------------------------------------------------------------------ lifecycle
    def register(self) -> str:
        info = self.detector()
        details = {
            "claude_code_version": info.version,
            "claude_ready": info.ready,
            "problems": info.problems,
            "max_concurrent_runs": self.settings.runner_max_concurrent_runs,
        }
        with session_scope(self.factory) as s:
            device = RunQueue(s, self.workspace_id).register_runner(self.name, "claude_code_local", details)
            self.runner_id = device.id
        if not info.ready:
            log.warning("Claude Code is not ready: %s", " ".join(info.problems))
        return self.runner_id

    async def run_forever(self) -> None:
        if self.settings.commercial_mode:
            raise SystemExit("The local Claude Code connector is disabled when AGENT_FLEET_COMMERCIAL_MODE=true.")
        await asyncio.to_thread(self.register)
        log.info("runner %s online (max %s concurrent runs)", self.name, self.settings.runner_max_concurrent_runs)
        last_recover = 0.0
        try:
            while not self._stopping:
                if time.monotonic() - last_recover > RECOVER_EVERY:
                    await asyncio.to_thread(self._recover)
                    last_recover = time.monotonic()
                await self.tick()
                await asyncio.sleep(self.settings.runner_poll_seconds)
        finally:
            await self.shutdown()

    async def tick(self) -> str | None:
        """Heartbeat, then claim one run if there is capacity. Returns the claimed run id."""
        self.active = {k: t for k, t in self.active.items() if not t.done()}
        busy = bool(self.active)
        await asyncio.to_thread(self._heartbeat, busy)
        if len(self.active) >= self.settings.runner_max_concurrent_runs:
            return None
        run_id = await asyncio.to_thread(self._claim)
        if run_id:
            self.active[run_id] = asyncio.create_task(self.execute(run_id), name=f"run-{run_id}")
        return run_id

    async def shutdown(self) -> None:
        self._stopping = True
        for task in self.active.values():
            task.cancel()
        if self.active:
            await asyncio.gather(*self.active.values(), return_exceptions=True)
        if self.runner_id:
            with session_scope(self.factory) as s:
                RunQueue(s, self.workspace_id).mark_offline(self.runner_id)

    def _heartbeat(self, busy: bool) -> None:
        assert self.runner_id
        with session_scope(self.factory) as s:
            RunQueue(s, self.workspace_id).heartbeat(self.runner_id, busy)

    def _recover(self) -> None:
        with session_scope(self.factory) as s:
            # Never recover a run this runner is still executing (for example after the computer slept).
            changed = RunQueue(s, self.workspace_id).recover(skip_run_ids=set(self.active))
        if changed:
            log.warning("recovered %d run(s) left by a stopped runner", len(changed))

    def _claim(self) -> str | None:
        assert self.runner_id
        with session_scope(self.factory) as s:
            run = RunQueue(s, self.workspace_id).claim_next(self.runner_id)
            return run.id if run else None

    # ------------------------------------------------------------------ one run
    async def execute(self, run_id: str) -> None:
        mapper: StreamMapper | None = None
        outcome: ExecutionOutcome | None = None
        try:
            info = await asyncio.to_thread(self.detector)
            if not info.ready:
                await asyncio.to_thread(self._fail, run_id, "Claude Code is not ready. " + " ".join(info.problems))
                return
            command = self.claude_command or [str(info.executable)]
            prepared = await asyncio.to_thread(self._prepare, run_id)
            if prepared is None:
                return
            request, root_agent_id, agent_models = prepared
            mapper = StreamMapper(self.factory, self.workspace_id, run_id, root_agent_id, agent_models)
            runtime = ClaudeCodeLocalRuntime(command, self.settings, on_parse_issue=mapper.note_parse_issue)
            outcome = await runtime.execute(
                request,
                on_message=lambda m: asyncio.to_thread(mapper.handle, m),
                keep_going=lambda: asyncio.to_thread(self._keep_going, run_id),
            )
            await asyncio.to_thread(self._finish, run_id, outcome, mapper)
        except asyncio.CancelledError:
            log.warning("runner stopping; failing run %s", run_id)
            await asyncio.to_thread(self._fail, run_id, "The runner was stopped while the run was active.")
            raise
        except OSError as exc:
            await asyncio.to_thread(self._fail, run_id, f"Claude Code could not be started: {exc.strerror or exc}")
        except Exception as exc:
            log.exception("run %s failed in the runner", run_id)
            await asyncio.to_thread(self._fail, run_id, f"Runner error: {redact_text(str(exc), 500)}")

    def _prepare(self, run_id: str) -> tuple[ExecutionRequest, str, dict[str, str]] | None:
        defs = load_definitions()
        with session_scope(self.factory) as s:
            run = s.get(Run, run_id)
            if run is None or run.status in RUN_TERMINAL:
                return None
            run_dir = self.settings.data_dir / "runs" / run.id
            run_dir.mkdir(parents=True, exist_ok=True)
            cwd = Path(run.workspace_path) if run.workspace_path else self.settings.data_dir / "workspaces" / run.id
            cwd.mkdir(parents=True, exist_ok=True)

            root_id = run.root_agent_id
            if root_id is None:
                root = AgentService(s, self.workspace_id, EventSource.RUNNER).register(
                    run.id,
                    "orchestrator",
                    "orchestrator",
                    run.orchestrator_model,
                    None,
                    status=AgentStatus.RUNNING,
                    external_ref="root",
                    idempotency_key="runner:root-agent",
                )
                root_id = root.id

            mcp_config = {
                "mcpServers": {
                    MCP_SERVER_NAME: {
                        "type": "stdio",
                        "command": self.python,
                        # -I (isolated mode): the workspace folder is NOT put on sys.path, so files in it
                        # (for example a folder named "mcp") cannot shadow or inject Python modules.
                        "args": ["-I", "-m", "agent_fleet.mcp"],
                        "env": {
                            "AGENT_FLEET_DATABASE_URL": self.settings.database_url,
                            "AGENT_FLEET_WORKSPACE_ID": self.workspace_id,
                            "AGENT_FLEET_RUN_ID": run.id,
                            "AGENT_FLEET_LOG_LEVEL": "WARNING",
                        },
                    }
                }
            }
            mcp_path = run_dir / "mcp.json"
            mcp_path.write_text(json.dumps(mcp_config, indent=2), encoding="utf-8")
            agents_path = run_dir / "agents.json"
            agents_path.write_text(agents_json(defs), encoding="utf-8")

            request = ExecutionRequest(
                run_id=run.id,
                workspace_id=self.workspace_id,
                prompt=build_prompt(run, root_id, defs),
                cwd=cwd,
                model=run.orchestrator_model,
                permission_policy=run.permission_policy,
                mcp_config_path=mcp_path,
                agents_path=agents_path,
                timeout_seconds=self.settings.run_timeout_seconds,
                max_concurrent_agents=run.max_concurrent_agents,
            )
            return request, root_id, {name: d.model for name, d in defs.items()}

    def _keep_going(self, run_id: str) -> bool:
        assert self.runner_id
        with session_scope(self.factory) as s:
            return RunQueue(s, self.workspace_id).renew_lease(run_id, self.runner_id)

    def _finish(self, run_id: str, outcome: ExecutionOutcome, mapper: StreamMapper) -> None:
        with session_scope(self.factory) as s:
            run = s.get(Run, run_id, populate_existing=True)
            if run is None:
                return
            events = EventService(s)
            if run.runner_device_id != self.runner_id:
                # Another runner took over this run after our lease expired; do not change its state.
                events.emit(
                    run,
                    EventType.EXECUTION_NOTICE,
                    "A previous runner attempt ended after it lost the run",
                    source=EventSource.RUNNER,
                    payload={"runner_id": self.runner_id, "exit_code": outcome.exit_code},
                )
                return
            events.emit(
                run,
                EventType.EXECUTION_SESSION_ENDED,
                f"Claude Code session ended (exit code {outcome.exit_code})",
                source=EventSource.RUNNER,
                agent_id=run.root_agent_id,
                payload={
                    "exit_code": outcome.exit_code,
                    "timed_out": outcome.timed_out,
                    "cancelled": outcome.cancelled,
                    "parse_issues": mapper.state.parse_issues,
                    "unknown_message_types": mapper.state.unknown_types,
                },
            )
            service = RunService(s, self.workspace_id, EventSource.RUNNER)
            if run.status not in RUN_TERMINAL:
                if outcome.success:
                    text = (outcome.result_text or "").strip() or "Claude Code finished without a final text result."
                    summary = redact_text(text, MAX_DESCRIPTION - 100)  # room for the truncation note
                    if run.status == RunStatus.PLANNING:
                        service.transition(run, RunStatus.RUNNING, "Claude Code session is running")
                    service.complete(run.id, summary)
                    events.emit(
                        run,
                        EventType.EXECUTION_NOTICE,
                        "The orchestrator did not call complete_run; the final Claude Code result was used",
                        source=EventSource.RUNNER,
                    )
                else:
                    run.error_message = explain_failure(outcome, mapper.state.api_errors)
                    service.fail(run.id, run.error_message)
            elif run.status == RunStatus.COMPLETED and not outcome.success and not outcome.cancelled:
                events.emit(
                    run,
                    EventType.EXECUTION_NOTICE,
                    "The run was completed by the orchestrator, but the Claude Code process ended with an error: "
                    + explain_failure(outcome, mapper.state.api_errors)[:500],
                    source=EventSource.RUNNER,
                )
            run.lease_expires_at = None
            events.emit(
                run,
                EventType.RUNNER_DISCONNECTED,
                "Runner finished the run",
                source=EventSource.RUNNER,
                payload={"runner_id": self.runner_id},
            )

    def _fail(self, run_id: str, reason: str) -> None:
        try:
            with session_scope(self.factory) as s:
                run = s.get(Run, run_id, populate_existing=True)
                if run is None or run.status in RUN_TERMINAL or run.runner_device_id != self.runner_id:
                    return
                # Failures here need a person (setup, start-up error), so the run is failed, not re-queued.
                run.error_message = reason
                RunService(s, self.workspace_id, EventSource.RUNNER).fail(run.id, reason)
        except Exception:
            log.exception("could not mark run %s as failed", run_id)
