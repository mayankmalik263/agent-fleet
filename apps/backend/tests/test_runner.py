import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest
from sqlalchemy import select

from agent_fleet.core.config import get_settings
from agent_fleet.core.enums import AgentStatus, EventSource, PermissionPolicy, RunStatus, TaskStatus
from agent_fleet.database import session_scope
from agent_fleet.models import Agent, Run, RunEvent, RunnerDevice, Task
from agent_fleet.providers import claude_cli
from agent_fleet.providers.base import ExecutionRequest
from agent_fleet.providers.claude_cli import ClaudeInstallation
from agent_fleet.providers.claude_code import build_args
from agent_fleet.runner.agent_defs import agents_json, load_definitions, parse_markdown
from agent_fleet.runner.worker import Runner
from agent_fleet.services.queue import RunQueue
from agent_fleet.services.runs import NewRun, RunService

from .conftest import FIXTURES

FAKE = [sys.executable, str(FIXTURES / "fake_claude.py")]
READY = ClaudeInstallation(found=True, executable="fake", version="9.9.9", logged_in=True)


def make_runner(factory, **settings_overrides) -> Runner:
    settings = get_settings()
    for key, value in settings_overrides.items():
        object.__setattr__(settings, key, value)
    return Runner(settings, factory=factory, claude_command=FAKE, detector=lambda: READY)


def queue_run(factory, ws, **kw) -> str:
    with session_scope(factory) as s:
        return RunService(s, ws, EventSource.API).create(NewRun(task_description="Test the fleet", **kw)).id


def run_events(factory, run_id) -> list[RunEvent]:
    with session_scope(factory) as s:
        return list(s.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.sequence_number)))


async def claim_and_execute(runner: Runner) -> str:
    await asyncio.to_thread(runner.register)
    run_id = await runner.tick()
    assert run_id, "runner should claim the queued run"
    await runner.active[run_id]
    return run_id


def get_run(factory, run_id) -> Run:
    with session_scope(factory) as s:
        return s.get(Run, run_id)


def test_e2e_fake_claude_through_real_mcp_server(session_factory, workspace_id, client, monkeypatch):
    """Dashboard -> queue -> runner -> (fake) Claude Code -> real MCP server -> database -> REST API."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "e2e")
    # Wait longer than the runner's 2 s watch interval after complete_run (regression: the runner must not
    # kill Claude Code just because the orchestrator already completed the run).
    monkeypatch.setenv("FAKE_CLAUDE_RESULT_DELAY", "5")
    response = client.post("/api/v1/runs", json={"task_description": "Review the repository", "title": "E2E"})
    assert response.status_code == 201
    run_id = response.json()["id"]

    runner = make_runner(session_factory, run_timeout_seconds=120)
    assert asyncio.run(claim_and_execute(runner)) == run_id

    snap = client.get(f"/api/v1/runs/{run_id}/snapshot").json()
    assert snap["run"]["status"] == "completed", snap["run"]["error_message"]
    assert snap["run"]["final_summary"] == "All four agents finished."
    assert snap["run"]["session_id"]
    assert snap["run"]["usage_json"]["cost_is_estimate"] is True
    assert snap["run"]["usage_json"]["estimated_cost_usd"] == 0.0123
    names = sorted(a["name"] for a in snap["agents"])
    assert names == ["analyst", "executor", "orchestrator", "researcher", "reviewer"]  # no duplicates from the stream
    root = next(a for a in snap["agents"] if a["name"] == "orchestrator")
    # Two root messages (20+10 in, 7+5 out). Thinking is ignored; usage is counted once per message id.
    assert root["input_tokens"] == 30 and root["output_tokens"] == 12
    assert all(a["parent_agent_id"] == root["id"] for a in snap["agents"] if a["id"] != root["id"])
    assert all(a["status"] == "completed" for a in snap["agents"])
    assert {a["model_alias"] for a in snap["agents"]} == {"sonnet", "haiku"}
    assert len(snap["tasks"]) == 4 and all(t["status"] == "completed" for t in snap["tasks"])
    assert snap["hierarchy"][0]["agent_id"] == root["id"] and len(snap["hierarchy"][0]["children"]) == 4

    events = client.get(f"/api/v1/runs/{run_id}/events?limit=500").json()["items"]
    seqs = [e["sequence_number"] for e in events]
    assert seqs == sorted(seqs) == list(range(1, len(seqs) + 1))
    types = [e["event_type"] for e in events]
    for expected in (
        "run.queued",
        "runner.connected",
        "execution.session_started",
        "run.started",
        "agent.created",
        "task.created",
        "tool.started",
        "tool.completed",
        "message.sent",
        "task.completed",
        "run.completed",
        "execution.usage_reported",
        "execution.session_ended",
        "runner.disconnected",
    ):
        assert expected in types, expected
    assert types.index("run.queued") < types.index("runner.connected") < types.index("run.completed")
    assert not any("SECRET REASONING" in json.dumps(e) for e in events)
    ended = next(e for e in events if e["event_type"] == "execution.session_ended")
    assert ended["payload"]["exit_code"] == 0 and ended["payload"]["cancelled"] is False
    messages = client.get(f"/api/v1/runs/{run_id}/messages").json()["items"]
    assert any(m["message_type"] == "instruction" for m in messages)  # delegation from the stream
    assert any(m["content"] == "researcher is halfway" for m in messages)  # from the MCP tool
    # Agent tool calls of subagents are attributed to the subagent (parent_tool_use_id).
    researcher = next(a for a in snap["agents"] if a["name"] == "researcher")
    assert any(e["event_type"] == "tool.started" and e["agent_id"] == researcher["id"] for e in events)


def test_mcp_server_starts_from_a_hostile_workspace(session_factory, workspace_id, tmp_path):
    """Regression: a workspace that contains a folder named 'mcp' (or any module) must not shadow the
    MCP SDK or inject code into the Agent Fleet MCP server that Claude Code starts in that folder."""
    import subprocess

    workspace = tmp_path / "workspaces" / "hostile"
    (workspace / "mcp").mkdir(parents=True)
    (workspace / "mcp" / "__init__.py").write_text("raise RuntimeError('workspace code was imported')")
    run_id = queue_run(session_factory, workspace_id, workspace_path=str(workspace))
    runner = make_runner(session_factory)
    runner.register()
    runner._claim()
    request, _, _ = runner._prepare(run_id)
    server = json.loads(request.mcp_config_path.read_text())["mcpServers"]["agent-fleet"]
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
    }
    proc = subprocess.run(
        [server["command"], *server["args"]],
        input=json.dumps(init) + "\n",
        cwd=workspace,
        env={**__import__("os").environ, **server["env"]},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "workspace code was imported" not in proc.stderr
    assert json.loads(proc.stdout.splitlines()[0])["result"]["serverInfo"]["name"] == "agent-fleet"


def test_runner_completes_with_result_text_when_orchestrator_does_not(session_factory, workspace_id, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "no_complete")
    run_id = queue_run(session_factory, workspace_id)
    asyncio.run(claim_and_execute(make_runner(session_factory)))
    run = get_run(session_factory, run_id)
    assert run.status == RunStatus.COMPLETED and run.final_summary == "Final answer from Claude Code."
    assert any("did not call complete_run" in e.message for e in run_events(session_factory, run_id))


def test_malformed_and_unknown_stream_lines_are_tolerated(session_factory, workspace_id, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "malformed")
    run_id = queue_run(session_factory, workspace_id)
    asyncio.run(claim_and_execute(make_runner(session_factory)))
    events = run_events(session_factory, run_id)
    ended = next(e for e in events if e.event_type == "execution.session_ended")
    assert ended.payload_json["parse_issues"] == 2
    assert ended.payload_json["unknown_message_types"] == {"brand_new_type": 1, "system/future_subtype": 1}
    assert any(e.event_type == "tool.failed" for e in events)
    assert get_run(session_factory, run_id).status == RunStatus.COMPLETED


def test_process_crash_fails_run(session_factory, workspace_id, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "crash")
    run_id = queue_run(session_factory, workspace_id)
    asyncio.run(claim_and_execute(make_runner(session_factory)))
    run = get_run(session_factory, run_id)
    assert run.status == RunStatus.FAILED
    assert "exited with code 3" in run.error_message and "something broke" in run.error_message


def test_authentication_error_is_explained(session_factory, workspace_id, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "auth")
    run_id = queue_run(session_factory, workspace_id)
    asyncio.run(claim_and_execute(make_runner(session_factory)))
    run = get_run(session_factory, run_id)
    assert run.status == RunStatus.FAILED and "not signed in" in run.error_message


def test_timeout_stops_process_and_fails_run(session_factory, workspace_id, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "hang")
    run_id = queue_run(session_factory, workspace_id)
    asyncio.run(claim_and_execute(make_runner(session_factory, run_timeout_seconds=3)))
    run = get_run(session_factory, run_id)
    assert run.status == RunStatus.FAILED and "did not finish within 3 seconds" in run.error_message
    ended = next(e for e in run_events(session_factory, run_id) if e.event_type == "execution.session_ended")
    assert ended.payload_json["timed_out"] is True


def test_cancellation_stops_process(session_factory, workspace_id, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "hang")
    run_id = queue_run(session_factory, workspace_id)
    runner = make_runner(session_factory, run_timeout_seconds=120)

    def cancel_soon() -> None:
        import time

        time.sleep(3)
        with session_scope(session_factory) as s:
            RunService(s, workspace_id, EventSource.API).cancel(run_id)

    threading.Thread(target=cancel_soon, daemon=True).start()
    asyncio.run(claim_and_execute(runner))
    run = get_run(session_factory, run_id)
    assert run.status == RunStatus.CANCELLED
    ended = next(e for e in run_events(session_factory, run_id) if e.event_type == "execution.session_ended")
    assert ended.payload_json["cancelled"] is True
    with session_scope(session_factory) as s:
        root = s.get(Agent, run.root_agent_id)
        assert root.status == AgentStatus.CANCELLED


def test_not_ready_claude_fails_with_setup_message(session_factory, workspace_id):
    run_id = queue_run(session_factory, workspace_id)
    missing = ClaudeInstallation(found=False, problems=["Claude Code was not found. Install it."])
    runner = Runner(get_settings(), factory=session_factory, claude_command=FAKE, detector=lambda: missing)
    asyncio.run(claim_and_execute(runner))
    run = get_run(session_factory, run_id)
    assert run.status == RunStatus.FAILED and "Claude Code was not found" in run.error_message


def test_two_runners_never_claim_the_same_run(session_factory, workspace_id):
    run_id = queue_run(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        q = RunQueue(s, workspace_id)
        a = q.register_runner("a", "claude_code_local").id
        b = q.register_runner("b", "claude_code_local").id
    results: list[str | None] = []

    def claim(runner_id: str) -> None:
        with session_scope(session_factory) as s:
            run = RunQueue(s, workspace_id).claim_next(runner_id)
            results.append(run.id if run else None)

    threads = [threading.Thread(target=claim, args=(rid,)) for rid in (a, b, a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(run_id) == 1 and results.count(None) == 3
    assert sum(1 for e in run_events(session_factory, run_id) if e.event_type == "runner.connected") == 1


def test_claude_code_runs_are_never_claimed(session_factory, workspace_id):
    from agent_fleet.core.enums import RunSource

    with session_scope(session_factory) as s:
        RunService(s, workspace_id, EventSource.MCP).create(
            NewRun(task_description="mine", source=RunSource.CLAUDE_CODE)
        )
        rid = RunQueue(s, workspace_id).register_runner("r", "claude_code_local").id
        assert RunQueue(s, workspace_id).claim_next(rid) is None


def test_expired_lease_recovery(session_factory, workspace_id):
    from datetime import timedelta

    from agent_fleet.core.time import utcnow

    started = queue_run(session_factory, workspace_id)
    fresh = queue_run(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        q = RunQueue(s, workspace_id)
        rid = q.register_runner("r", "claude_code_local").id
        for _ in (started, fresh):
            assert q.claim_next(rid) is not None
        s.get(Run, started).session_id = "had-a-session"
        # The runner died: no heartbeat for longer than a lease.
        s.get(RunnerDevice, rid).last_seen_at = utcnow() - timedelta(seconds=600)
        for run_id in (started, fresh):
            s.get(Run, run_id).lease_expires_at = utcnow() - timedelta(seconds=1)
    with session_scope(session_factory) as s:
        changed = RunQueue(s, workspace_id).recover()
    assert set(changed) == {started, fresh}
    assert get_run(session_factory, started).status == RunStatus.FAILED  # a session ran: never re-run it
    assert get_run(session_factory, fresh).status == RunStatus.QUEUED  # nothing ran yet: safe to retry


def test_cli_arguments_are_safe(tmp_path):
    settings = get_settings()
    req = ExecutionRequest(
        run_id="r",
        workspace_id="w",
        prompt="p",
        cwd=tmp_path,
        model="sonnet",
        permission_policy=PermissionPolicy.READ_ONLY,
        mcp_config_path=tmp_path / "m.json",
        agents_path=tmp_path / "a.json",
        timeout_seconds=60,
        max_concurrent_agents=4,
    )
    args = build_args(["claude"], req, settings)
    joined = " ".join(args)
    for required in (
        "-p",
        "--output-format stream-json",
        "--verbose",
        "--model sonnet",
        "--mcp-config",
        "--strict-mcp-config",
        "--permission-mode dontAsk",
        "--permission-prompts none",
    ):
        assert required in joined
    assert "--dangerously-skip-permissions" not in args and "bypassPermissions" not in joined
    assert "--bare" not in args
    assert args[args.index("--tools") + 1] == "Read,Grep,Glob,Agent"
    edit = build_args(
        ["claude"], ExecutionRequest(**{**req.__dict__, "permission_policy": PermissionPolicy.WORKSPACE_EDIT}), settings
    )
    assert "acceptEdits" in edit and "Bash(rm *)" in edit[edit.index("--disallowedTools") + 1]


def test_agent_definitions_load_with_expected_models():
    defs = load_definitions()
    assert {n: d.model for n, d in defs.items()} == {
        "researcher": "haiku",
        "analyst": "haiku",
        "executor": "sonnet",
        "reviewer": "sonnet",
    }
    payload = json.loads(agents_json(defs))
    assert payload["reviewer"]["disallowedTools"] == ["Edit", "Write", "NotebookEdit", "Bash", "Agent"]
    with pytest.raises(ValueError):
        parse_markdown("no frontmatter")


def test_executable_detection_prefers_native_binary_over_cmd_shim(tmp_path, monkeypatch):
    shim_dir = tmp_path / "npm"
    native = shim_dir / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    native.parent.mkdir(parents=True)
    native.write_text("")
    (shim_dir / "claude.cmd").write_text("@echo off")
    settings = get_settings().model_copy(update={"claude_path": None})
    monkeypatch.setattr(
        claude_cli.shutil, "which", lambda name: str(shim_dir / "claude.cmd") if name == "claude" else None
    )
    monkeypatch.setattr(claude_cli.sys, "platform", "win32")
    assert claude_cli.find_executable(settings) == str(native)
    explicit = get_settings().model_copy(update={"claude_path": str(native)})
    assert claude_cli.find_executable(explicit) == str(native)
    missing = get_settings().model_copy(update={"claude_path": str(tmp_path / "nope.exe")})
    assert claude_cli.find_executable(missing) is None


def test_detect_reports_missing_installation(monkeypatch):
    settings = get_settings().model_copy(update={"claude_path": "Z:/definitely/missing/claude.exe"})
    info = claude_cli.detect(settings)
    assert not info.ready and "not found" in info.problems[0]


def test_child_env_removes_api_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    env = claude_cli.child_env(get_settings())
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env


@pytest.mark.real_claude
def test_real_claude_smoke(session_factory, workspace_id):
    """Opt-in: AGENT_FLEET_REAL_CLAUDE_SMOKE=1 uv run pytest -m real_claude. Uses your Claude subscription."""
    import os

    if os.environ.get("AGENT_FLEET_REAL_CLAUDE_SMOKE") != "1":
        pytest.skip("set AGENT_FLEET_REAL_CLAUDE_SMOKE=1 to run a real Claude Code session")
    settings = get_settings().model_copy(update={"claude_path": None, "run_timeout_seconds": 600})
    info = claude_cli.detect(settings)
    if not info.ready:
        pytest.skip("Claude Code not installed or not signed in: " + " ".join(info.problems))
    run_id = queue_run(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        s.get(Run, run_id).task_description = "Reply with the single word OK. Do not delegate."
    runner = Runner(settings, factory=session_factory, detector=lambda: info)
    asyncio.run(claim_and_execute(runner))
    run = get_run(session_factory, run_id)
    assert run.status == RunStatus.COMPLETED, run.error_message
    with session_scope(session_factory) as s:
        assert s.scalars(select(Task)).all() is not None
        _ = TaskStatus
    _ = Path
