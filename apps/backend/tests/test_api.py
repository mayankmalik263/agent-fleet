import uuid

from agent_fleet.core.enums import EventSource, RunSource
from agent_fleet.database import session_scope
from agent_fleet.services.agents import AgentService
from agent_fleet.services.runs import NewRun, RunService
from agent_fleet.services.tasks import TaskService


def create(client, **body):
    r = client.post("/api/v1/runs", json={"task_description": "Analyse logs", **body})
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_status(client):
    assert client.get("/health").json() == {"status": "ok"}
    status = client.get("/api/v1/system/status").json()
    assert status["mode"] == "local" and status["database"] == "sqlite"
    providers = {p["provider"]: p for p in status["providers"]}
    # Tests point AGENT_FLEET_CLAUDE_PATH at a missing file, so the provider is honestly "disconnected".
    assert providers["claude_code_local"]["status"] == "disconnected"
    assert providers["anthropic_api"]["status"] == "unsupported_in_local_mode"
    assert status["runner"] == {"runners": [], "any_online": False, "queued_runs": 0, "active_runs": 0}
    assert status["integrations"][0]["name"] == "graphify"


def test_create_list_filter_sort_paginate(client):
    a = create(client, title="Alpha")
    b = create(client, title="Beta")
    assert a["status"] == "queued" and a["event_count"] == 2 and a["source"] == "dashboard"
    page = client.get("/api/v1/runs?limit=1&offset=0&sort=title").json()
    assert page["total"] == 2 and page["limit"] == 1 and page["items"][0]["title"] == "Alpha"
    assert client.get("/api/v1/runs?sort=-title").json()["items"][0]["id"] == b["id"]
    assert client.get("/api/v1/runs?search=bet").json()["total"] == 1
    assert client.get("/api/v1/runs?status=completed").json()["total"] == 0
    bad = client.get("/api/v1/runs?sort=password")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_failed"


def test_validation_errors_are_consistent(client):
    r = client.post("/api/v1/runs", json={"task_description": ""})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"
    r = client.post("/api/v1/runs", json={"task_description": "x", "permission_policy": "workspace_edit"})
    assert r.status_code == 422 and "confirm" in r.json()["error"]["message"]
    r = client.post("/api/v1/runs", json={"task_description": "x", "execution_provider": "anthropic_api"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "runtime_unavailable"
    r = client.get(f"/api/v1/runs/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.get("/api/v1/runs/not-a-uuid").status_code == 422


def test_cancel_and_invalid_transition(client):
    run = create(client)
    assert client.post(f"/api/v1/runs/{run['id']}/cancel").json()["status"] == "cancelled"
    again = client.post(f"/api/v1/runs/{run['id']}/cancel")
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_transition"


def _populated_run(session_factory, workspace_id):
    with session_scope(session_factory) as s:
        run = RunService(s, workspace_id, EventSource.MCP).create(
            NewRun(task_description="t", source=RunSource.CLAUDE_CODE)
        )
        agents = AgentService(s, workspace_id, EventSource.MCP)
        root = agents.register(run.id, "orchestrator", "orchestrator", "sonnet")
        worker = agents.register(run.id, "analyst", "analyst", "haiku", root.id)
        task = TaskService(s, workspace_id, EventSource.MCP).create(run.id, "Analyse", "Analyse data", worker.id)
        return run.id, root.id, worker.id, task.id


def test_agents_tasks_messages_endpoints(client, session_factory, workspace_id):
    run_id, root_id, worker_id, task_id = _populated_run(session_factory, workspace_id)
    assert len(client.get(f"/api/v1/runs/{run_id}/agents").json()) == 2
    details = client.get(f"/api/v1/agents/{worker_id}").json()
    assert details["parent"]["id"] == root_id and details["tasks"][0]["id"] == task_id

    r = client.patch(f"/api/v1/agents/{worker_id}", json={"status": "running"})
    assert r.status_code == 200 and r.json()["status"] == "running"
    r = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "in_progress", "progress_percentage": 30})
    assert r.json()["progress_percentage"] == 30
    assert client.patch(f"/api/v1/tasks/{task_id}", json={"progress_percentage": 101}).status_code == 422
    assert client.get(f"/api/v1/runs/{run_id}/tasks?status=in_progress").json()[0]["id"] == task_id
    assert client.get(f"/api/v1/runs/{run_id}/messages").json()["total"] == 0

    snap = client.get(f"/api/v1/runs/{run_id}/snapshot").json()
    assert snap["agent_status_counts"] == {"running": 2}
    assert snap["task_status_counts"] == {"in_progress": 1}
    events = client.get(f"/api/v1/runs/{run_id}/events?event_type=task.started").json()
    assert events["total"] == 1 and events["items"][0]["task_id"] == task_id

    overview = client.get("/api/v1/overview").json()
    assert overview["total_agents"] == 2 and overview["running_agents"] == 2 and overview["total_tasks"] == 1


def test_workspace_header_isolation(client, session_factory, workspace_id, other_workspace):
    run_id, *_ = _populated_run(session_factory, workspace_id)
    headers = {"X-Agent-Fleet-Workspace": other_workspace}
    assert client.get(f"/api/v1/runs/{run_id}", headers=headers).status_code == 404
    assert client.get("/api/v1/runs", headers=headers).json()["total"] == 0
    unknown = {"X-Agent-Fleet-Workspace": str(uuid.uuid4())}
    assert client.get("/api/v1/runs", headers=unknown).status_code == 404


def _sse_ids(body: str) -> list[int]:
    return [int(line[4:]) for line in body.splitlines() if line.startswith("id: ")]


def test_sse_replay_cursor_and_end(client):
    run = create(client)
    client.post(f"/api/v1/runs/{run['id']}/cancel")
    with client.stream("GET", f"/api/v1/runs/{run['id']}/events/stream") as s:
        assert s.headers["content-type"].startswith("text/event-stream")
        body = "".join(s.iter_text())
    ids = _sse_ids(body)
    assert ids == list(range(1, ids[-1] + 1)) and "event: end" in body
    with client.stream("GET", f"/api/v1/runs/{run['id']}/events/stream", headers={"Last-Event-ID": "2"}) as s:
        resumed = _sse_ids("".join(s.iter_text()))
    assert resumed == ids[2:]  # no duplicates, no gaps after the cursor
    with client.stream("GET", f"/api/v1/runs/{run['id']}/events/stream?after=1") as s:
        assert _sse_ids("".join(s.iter_text())) == ids[1:]
    assert client.get(f"/api/v1/runs/{uuid.uuid4()}/events/stream").status_code == 404


def test_hook_events_attach_to_session_run(client, session_factory, workspace_id):
    with session_scope(session_factory) as s:
        run = RunService(s, workspace_id, EventSource.MCP).create(
            NewRun(task_description="t", source=RunSource.CLAUDE_CODE, session_id="sess-42")
        )
        AgentService(s, workspace_id, EventSource.MCP).register(run.id, "orchestrator", "orchestrator", "sonnet")
        run_id = run.id
    hook = "/api/v1/integrations/claude-code/hooks"
    start = {"hook_event_name": "SubagentStart", "session_id": "sess-42", "agent_id": "a1", "agent_type": "plugin:rev"}
    assert client.post(hook, json=start).json()["linked"] is True
    assert client.post(hook, json=start).json()["linked"] is True  # idempotent
    client.post(hook, json={**start, "hook_event_name": "SubagentStop"})
    assert client.post(hook, json={"hook_event_name": "SubagentStart", "session_id": "other"}).json()["linked"] is False
    agents = client.get(f"/api/v1/runs/{run_id}/agents").json()
    sub = [a for a in agents if a["name"] == "plugin-rev"]
    assert len(sub) == 1 and sub[0]["status"] == "completed"


def test_request_log_never_contains_query_strings(client, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="agent_fleet.api"):
        client.get("/api/v1/runs?search=sk-ant-secretsecret123")
    assert "sk-ant" not in caplog.text and "/api/v1/runs" in caplog.text
