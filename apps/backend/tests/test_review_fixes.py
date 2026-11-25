"""Regression tests for the findings of the independent backend review."""

import asyncio
import subprocess
import sys
import time
from datetime import timedelta

import pytest

from agent_fleet.core.enums import EventSource, RunSource, RunStatus
from agent_fleet.core.errors import InvalidTransitionError
from agent_fleet.core.redaction import REDACTED, redact_text, sanitize
from agent_fleet.core.time import utcnow
from agent_fleet.database import session_scope
from agent_fleet.models import Run
from agent_fleet.runner.agent_defs import agents_json, parse_markdown
from agent_fleet.services.agents import AgentService
from agent_fleet.services.events import EventService
from agent_fleet.services.hooks import record_hook_event
from agent_fleet.services.queue import RunQueue
from agent_fleet.services.runs import NewRun, RunService
from agent_fleet.services.tasks import TaskService

from .test_runner import claim_and_execute, get_run, make_runner, queue_run


def _alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


@pytest.mark.skipif(sys.platform != "win32", reason="uses tasklist")
def test_runner_shutdown_kills_claude_process(session_factory, workspace_id, monkeypatch, tmp_path):
    pid_file = tmp_path / "pid.txt"
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "hang")
    monkeypatch.setenv("FAKE_CLAUDE_PID_FILE", str(pid_file))
    run_id = queue_run(session_factory, workspace_id)
    runner = make_runner(session_factory, run_timeout_seconds=120)

    async def scenario() -> None:
        await asyncio.to_thread(runner.register)
        await runner.tick()
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text():
                break
            await asyncio.sleep(0.1)
        await asyncio.sleep(1)
        await runner.shutdown()

    asyncio.run(scenario())
    pid = int(pid_file.read_text())
    time.sleep(1)
    assert not _alive(pid), "Claude Code must not keep running after the runner stops"
    assert get_run(session_factory, run_id).status == RunStatus.FAILED


def test_long_stderr_line_keeps_timeout_working(session_factory, workspace_id, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "noisy_hang")
    run_id = queue_run(session_factory, workspace_id)
    started = time.monotonic()
    asyncio.run(claim_and_execute(make_runner(session_factory, run_timeout_seconds=3)))
    assert time.monotonic() - started < 40
    run = get_run(session_factory, run_id)
    assert run.status == RunStatus.FAILED and "did not finish within 3 seconds" in run.error_message


@pytest.mark.parametrize("scenario", ["long_result", "blank_result"])
def test_successful_run_with_unusual_result_text_completes(session_factory, workspace_id, monkeypatch, scenario):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", scenario)
    run_id = queue_run(session_factory, workspace_id)
    asyncio.run(claim_and_execute(make_runner(session_factory)))
    run = get_run(session_factory, run_id)
    assert run.status == RunStatus.COMPLETED, run.error_message
    assert run.final_summary and len(run.final_summary) <= 20_100


def test_untrusted_host_header_is_rejected(client):
    assert client.get("/health", headers={"Host": "attacker.example"}).status_code == 400
    assert client.get("/health", headers={"Host": "127.0.0.1:8420"}).status_code == 200


def test_recover_keeps_runs_of_a_live_runner(session_factory, workspace_id):
    run_id = queue_run(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        q = RunQueue(s, workspace_id)
        rid = q.register_runner("r", "claude_code_local").id
        q.claim_next(rid)
        run = s.get(Run, run_id)
        run.session_id = "s"
        run.lease_expires_at = utcnow() - timedelta(seconds=1)
    with session_scope(session_factory) as s:
        assert RunQueue(s, workspace_id).recover() == []  # the runner's heartbeat is fresh
        assert RunQueue(s, workspace_id).recover(skip_run_ids={run_id}) == []


def test_bad_task_status_filter_is_422(client):
    run = client.post("/api/v1/runs", json={"task_description": "x"}).json()
    r = client.get(f"/api/v1/runs/{run['id']}/tasks?status=bogus")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"


def test_cancelled_task_cannot_receive_a_result(session_factory, workspace_id):
    with session_scope(session_factory) as s:
        run = RunService(s, workspace_id, EventSource.MCP).create(
            NewRun(task_description="t", source=RunSource.CLAUDE_CODE)
        )
        root = AgentService(s, workspace_id, EventSource.MCP).register(run.id, "orchestrator", "orchestrator", "sonnet")
        tasks = TaskService(s, workspace_id, EventSource.MCP)
        task = tasks.create(run.id, "t", "d", root.id)
        tasks.update_status(run.id, task.id, "cancelled")
        with pytest.raises(InvalidTransitionError):
            tasks.submit_result(run.id, task.id, root.id, "late")


def test_hook_subagent_never_becomes_root(session_factory, workspace_id):
    with session_scope(session_factory) as s:
        run = RunService(s, workspace_id, EventSource.MCP).create(
            NewRun(task_description="t", source=RunSource.CLAUDE_CODE, session_id="sess-x")
        )
        record_hook_event(
            s,
            workspace_id,
            {"hook_event_name": "SubagentStart", "session_id": "sess-x", "agent_id": "a1", "agent_type": "explorer"},
        )
        assert run.root_agent_id is None
        root = AgentService(s, workspace_id, EventSource.MCP).register(run.id, "orchestrator", "orchestrator", "sonnet")
        assert run.root_agent_id == root.id


def test_agent_definitions_never_pass_permission_mode():
    definition = parse_markdown("---\nname: x\ndescription: y\npermissionMode: bypassPermissions\n---\nbody")
    payload = agents_json({"x": definition})
    assert "permissionMode" not in payload and "bypassPermissions" not in payload


def test_redaction_covers_camel_case_and_common_tokens():
    out = sanitize({"accessToken": "a", "idToken": "b", "input_tokens": 3, "output_tokens": 4})
    assert out == {"accessToken": REDACTED, "idToken": REDACTED, "input_tokens": 3, "output_tokens": 4}
    text = redact_text("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop aws AKIAABCDEFGHIJKLMNOP")
    assert "eyJ" not in text and "AKIA" not in text


def test_sse_waits_for_runner_final_events(session_factory, workspace_id):
    from agent_fleet.api.stream import _stream_finished

    run_id = queue_run(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        q = RunQueue(s, workspace_id)
        rid = q.register_runner("r", "claude_code_local").id
        q.claim_next(rid)
        run = s.get(Run, run_id)
        svc = RunService(s, workspace_id, EventSource.MCP)
        svc.transition(run, RunStatus.RUNNING, "go")
        svc.complete(run_id, "done")
        assert not _stream_finished(s, run, run.event_seq)  # usage and session-end events are still coming
        EventService(s).emit(run, "runner.disconnected", "bye", source=EventSource.RUNNER)
        assert _stream_finished(s, run, run.event_seq)
