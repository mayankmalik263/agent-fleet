import os
import sys
import uuid

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from agent_fleet.mcp.server import ToolContext, build_server

pytestmark = pytest.mark.anyio

ALL_TOOLS = {
    "create_run",
    "register_agent",
    "update_agent_status",
    "create_task",
    "update_task_status",
    "submit_task_result",
    "send_agent_message",
    "append_run_event",
    "get_run_snapshot",
    "get_agent_details",
    "complete_run",
    "fail_run",
    "query_code_graph",
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(session_factory, workspace_id):
    return build_server(ToolContext(workspace_id, None, session_factory))


async def call(server, tool, /, **args):
    return (await server.call_tool(tool, args)).structured_content


async def expect_error(server, tool, match, /, **args):
    with pytest.raises(ToolError, match=match) as exc:
        await server.call_tool(tool, args)
    assert not isinstance(exc.value, UnexpectedToolError), "expected errors must not look like crashes"


async def test_tools_are_registered_with_descriptions(server):
    tools = await server.list_tools()
    assert {t.name for t in tools} == ALL_TOOLS
    assert all(t.description and len(t.description) > 20 for t in tools)


async def test_every_tool_round_trip(server, session_factory):
    run = await call(server, "create_run", task_description="Write a report", session_id="sess-1")
    rid = run["run_id"]
    assert run["status"] == "running"
    root = await call(
        server, "register_agent", run_id=rid, name="orchestrator", role="orchestrator", model_alias="sonnet"
    )
    assert root["status"] == "running"
    worker = await call(
        server,
        "register_agent",
        run_id=rid,
        name="researcher",
        role="researcher",
        model_alias="haiku",
        parent_agent_id=root["agent_id"],
    )
    assert worker["status"] == "queued"
    assert (await call(server, "update_agent_status", run_id=rid, agent_id=worker["agent_id"], status="running"))[
        "status"
    ] == "running"
    task = await call(
        server,
        "create_task",
        run_id=rid,
        title="Research",
        description="Find facts",
        assigned_agent_id=worker["agent_id"],
        priority="high",
    )
    progressed = await call(
        server, "update_task_status", run_id=rid, task_id=task["task_id"], status="in_progress", progress_percentage=25
    )
    assert progressed == {"task_id": task["task_id"], "status": "in_progress", "progress_percentage": 25}
    msg = await call(
        server,
        "send_agent_message",
        run_id=rid,
        sender_agent_id=worker["agent_id"],
        receiver_agent_id=root["agent_id"],
        content="Found 2 facts",
        message_type="status",
        task_id=task["task_id"],
    )
    assert msg["message_id"]
    event = await call(
        server,
        "append_run_event",
        run_id=rid,
        event_type="tool.started",
        message="Grep for facts",
        agent_id=worker["agent_id"],
        payload={"tool_name": "Grep"},
    )
    assert event["event_type"] == "tool.started" and event["payload"] == {"tool_name": "Grep"}
    result = await call(
        server,
        "submit_task_result",
        run_id=rid,
        task_id=task["task_id"],
        agent_id=worker["agent_id"],
        result_summary="Two facts",
        result_payload={"facts": [1, 2]},
    )
    assert result["status"] == "completed" and result["result_payload"] == {"facts": [1, 2]}
    details = await call(server, "get_agent_details", run_id=rid, agent_id=worker["agent_id"])
    assert details["parent"]["id"] == root["agent_id"] and details["tool_events"][0]["event_type"] == "tool.started"
    snap = await call(server, "get_run_snapshot", run_id=rid)
    assert len(snap["agents"]) == 2 and snap["tasks"][0]["status"] == "completed"
    assert snap["hierarchy"][0]["children"][0]["agent_id"] == worker["agent_id"]
    assert snap["event_counts"]["message.sent"] == 1
    done = await call(server, "complete_run", run_id=rid, final_summary="Report finished")
    assert done["status"] == "completed" and done["completed_at"]
    await expect_error(server, "fail_run", "invalid_transition", run_id=rid, error_message="late")
    await expect_error(server, "query_code_graph", "no workspace_path", run_id=rid, command="query", arguments=["x"])

    other = await call(server, "create_run", task_description="Second")
    failed = await call(server, "fail_run", run_id=other["run_id"], error_message="Could not finish")
    assert failed["status"] == "failed"


async def test_invalid_arguments_and_missing_records(server):
    await expect_error(server, "get_run_snapshot", "not a valid UUID", run_id="abc")
    await expect_error(server, "get_run_snapshot", "not_found", run_id=str(uuid.uuid4()))
    rid = (await call(server, "create_run", task_description="x"))["run_id"]
    await expect_error(
        server,
        "register_agent",
        "not_found",
        run_id=rid,
        name="x",
        role="r",
        model_alias="sonnet",
        parent_agent_id=str(uuid.uuid4()),
    )
    await expect_error(server, "update_agent_status", "status", run_id=rid, agent_id=str(uuid.uuid4()), status="flying")
    await expect_error(
        server, "append_run_event", "cannot be appended", run_id=rid, event_type="run.completed", message="no"
    )
    await expect_error(server, "create_run", "task_description", task_description="")
    await expect_error(server, "create_run", "cross-workspace", task_description="x", workspace_id=str(uuid.uuid4()))


async def test_bound_session_is_confined_to_its_run(session_factory, workspace_id):
    free = build_server(ToolContext(workspace_id, None, session_factory))
    rid = (await call(free, "create_run", task_description="mine"))["run_id"]
    other = (await call(free, "create_run", task_description="other"))["run_id"]
    bound = build_server(ToolContext(workspace_id, rid, session_factory))
    await expect_error(bound, "create_run", "already belongs", task_description="recursive")
    await expect_error(bound, "get_run_snapshot", "only access run", run_id=other)
    assert (await call(bound, "get_run_snapshot", run_id=rid))["run"]["id"] == rid


async def test_workspace_scoping(session_factory, workspace_id, other_workspace):
    mine = build_server(ToolContext(workspace_id, None, session_factory))
    theirs = build_server(ToolContext(other_workspace, None, session_factory))
    rid = (await call(mine, "create_run", task_description="private"))["run_id"]
    await expect_error(theirs, "get_run_snapshot", "not_found", run_id=rid)


async def test_stdio_server_speaks_only_protocol_on_stdout(db_url, tmp_path):
    """Start the real server over stdio as Claude Code does, and use it."""
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters

    env = {**os.environ, "AGENT_FLEET_DATABASE_URL": db_url, "AGENT_FLEET_LOG_LEVEL": "INFO"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "agent_fleet.mcp"], env=env)
    with anyio.fail_after(60):
        async with Client(params) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert names == ALL_TOOLS
            res = await c.call_tool("create_run", {"task_description": "stdio check"})
            assert not res.is_error and res.structured_content["status"] == "running"
            bad = await c.call_tool("get_run_snapshot", {"run_id": "nope"})
            assert bad.is_error and "not a valid UUID" in bad.content[0].text


def test_stdout_carries_only_json_rpc(db_url):
    """Diagnostics must go to stderr: every stdout line must be a JSON-RPC message."""
    import json
    import subprocess

    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
    }
    env = {**os.environ, "AGENT_FLEET_DATABASE_URL": db_url, "AGENT_FLEET_LOG_LEVEL": "DEBUG"}
    proc = subprocess.run(
        [sys.executable, "-m", "agent_fleet.mcp"],
        input=json.dumps(init) + "\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, proc.stderr
    for line in lines:
        assert json.loads(line)["jsonrpc"] == "2.0"
    assert "agent-fleet MCP server starting" in proc.stderr
