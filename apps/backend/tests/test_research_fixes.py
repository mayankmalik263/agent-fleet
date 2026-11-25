"""Tests for the fixes found in the failed 'MCP research papers' run (2026-11-25):
no web tools, background subagents marked finished too early, no retry, no final report rules."""

import asyncio

from sqlalchemy import select

from agent_fleet.core.config import get_settings
from agent_fleet.core.enums import AgentStatus, EventSource, PermissionPolicy, RunSource, RunStatus, TaskStatus
from agent_fleet.database import session_scope
from agent_fleet.models import Agent, Run
from agent_fleet.runner.agent_defs import load_definitions
from agent_fleet.runner.policy import policy_args
from agent_fleet.runner.prompt import build_prompt
from agent_fleet.services.agents import AgentService
from agent_fleet.services.runs import NewRun, RunService
from agent_fleet.services.tasks import TaskService

from .test_runner import claim_and_execute, get_run, make_runner, queue_run


def _tools(args: list[str]) -> list[str]:
    return args[args.index("--tools") + 1].split(",")


def test_web_access_adds_web_tools_per_run(db_url):
    settings = get_settings()
    assert "WebSearch" not in _tools(policy_args(PermissionPolicy.READ_ONLY, settings, web_access=False))
    read_only = policy_args(PermissionPolicy.READ_ONLY, settings, web_access=True)
    assert {"WebSearch", "WebFetch"} <= set(_tools(read_only))
    assert "WebFetch" in read_only[read_only.index("--allowedTools") + 1]
    edit = policy_args(PermissionPolicy.WORKSPACE_EDIT, settings, web_access=True)
    assert "WebSearch" in _tools(edit)


def test_api_stores_web_access_and_prompt_mentions_it(client, session_factory, workspace_id):
    on = client.post("/api/v1/runs", json={"task_description": "Find papers", "web_access": True}).json()
    off = client.post("/api/v1/runs", json={"task_description": "Find papers"}).json()
    assert on["web_access"] is True and off["web_access"] is False  # default: AGENT_FLEET_ALLOW_WEB_TOOLS
    with session_scope(session_factory) as s:
        run = s.get(Run, on["id"])
        prompt = build_prompt(run, "root-id", load_definitions())
    assert "WebSearch and WebFetch are available" in prompt
    assert "FINAL REPORT" in prompt and "## Gaps and limits" in prompt


def test_runner_passes_web_tools_and_disables_background_subagents(session_factory, workspace_id, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "async_agent")
    run_id = queue_run(session_factory, workspace_id, web_access=True)
    asyncio.run(claim_and_execute(make_runner(session_factory)))
    run = get_run(session_factory, run_id)
    assert run.status == RunStatus.COMPLETED
    assert "WebSearch" in run.final_summary and "disable_background=1" in run.final_summary


def test_async_agent_launch_does_not_finish_the_subagent(session_factory, workspace_id, monkeypatch):
    """Regression: 'Async agent launched' was recorded as the subagent's end and as its result message."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "async_agent")
    run_id = queue_run(session_factory, workspace_id)
    runner = make_runner(session_factory)
    asyncio.run(claim_and_execute(runner))
    with session_scope(session_factory) as s:
        sub = s.scalars(select(Agent).where(Agent.run_id == run_id, Agent.name == "researcher")).one()
        # It stayed running until the run ended, then the run closed it (flagged implicit).
        assert sub.status == AgentStatus.COMPLETED
        events = RunService(s, workspace_id, EventSource.API).snapshot(run_id)
        texts = [m["content"] if isinstance(m, dict) else m.content for m in events["recent_messages"]]
    assert not any("Async agent launched" in t for t in texts)
    assert any(t == "Working." for t in texts)


def _finished_run_with_failed_task(factory, workspace_id) -> tuple[str, str]:
    with session_scope(factory) as s:
        runs = RunService(s, workspace_id, EventSource.API)
        run = runs.create(NewRun(task_description="Find MCP papers", title="Papers", web_access=False))
        agents = AgentService(s, workspace_id, EventSource.MCP)
        root = agents.register(run.id, "orchestrator", "orchestrator", "sonnet")
        worker = agents.register(run.id, "researcher", "researcher", "haiku", root.id)
        task = TaskService(s, workspace_id, EventSource.MCP).create(
            run.id, "Benchmarks", "Find benchmark papers", worker.id
        )
        TaskService(s, workspace_id, EventSource.MCP).update_status(run.id, task.id, TaskStatus.IN_PROGRESS)
        TaskService(s, workspace_id, EventSource.MCP).update_status(
            run.id, task.id, TaskStatus.FAILED, error_message="no web search tool"
        )
        run.status = RunStatus.FAILED
        return run.id, task.id


def test_retry_whole_run_and_one_task(client, session_factory, workspace_id):
    run_id, task_id = _finished_run_with_failed_task(session_factory, workspace_id)

    whole = client.post(f"/api/v1/runs/{run_id}/retry", json={"web_access": True})
    assert whole.status_code == 201, whole.text
    body = whole.json()
    assert body["retry_of_run_id"] == run_id and body["status"] == "queued"
    assert body["title"] == "Retry: Papers" and body["web_access"] is True
    assert body["task_description"] == "Find MCP papers"

    one = client.post(f"/api/v1/runs/{run_id}/retry", json={"task_id": task_id}).json()
    assert one["title"] == "Retry task: Benchmarks" and one["web_access"] is False
    assert "Find benchmark papers" in one["task_description"]
    assert "no web search tool" in one["task_description"]


def test_retry_rejects_active_and_claude_code_runs(client, session_factory, workspace_id):
    active = client.post("/api/v1/runs", json={"task_description": "x"}).json()
    assert client.post(f"/api/v1/runs/{active['id']}/retry", json={}).status_code == 422
    with session_scope(session_factory) as s:
        run = RunService(s, workspace_id, EventSource.MCP).create(
            NewRun(task_description="t", source=RunSource.CLAUDE_CODE)
        )
        run.status = RunStatus.COMPLETED
        cc_id = run.id
    assert client.post(f"/api/v1/runs/{cc_id}/retry", json={}).status_code == 422
    assert client.post(f"/api/v1/runs/{active['id']}/retry", json={"task_id": "nope"}).status_code in (404, 422)


def test_subagent_result_keeps_only_the_report():
    from agent_fleet.runner.event_mapper import clean_subagent_result

    raw = (
        "<tools-used-before-summary>WebFetch, WebSearch</tools-used-before-summary>\n  \n"
        "[Subagent hand-back] The text below is the final report of a subagent. The report follows:\n"
        "  I found nine papers.\n  \n  1. **Paper** https://arxiv.org/abs/1\nagentId: af0ce14c12a135d6f\n"
        "<usage>subagent_tokens: 33769\ntool_uses: 18</usage>"
    )
    assert clean_subagent_result(raw) == "I found nine papers.\n\n1. **Paper** https://arxiv.org/abs/1"
    assert clean_subagent_result("Plain answer.") == "Plain answer."
