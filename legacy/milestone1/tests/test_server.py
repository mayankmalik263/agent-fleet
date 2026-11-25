import uuid

import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from agent_fleet.server import build_server
from agent_fleet.store import RunStore

pytestmark = pytest.mark.anyio  # anyio ships with mcp; no pytest-asyncio needed


@pytest.fixture
def server(tmp_path):
    return build_server(RunStore(tmp_path / "test.db"))


async def test_tools_registered(server):
    names = {t.name for t in await server.list_tools()}
    assert names == {"create_run", "append_run_event", "get_run", "list_run_events", "finish_run"}


async def test_tool_roundtrip(server):
    run = (await server.call_tool("create_run", {"task": "demo", "source": "claude_code"})).structured_content
    rid = run["run_id"]
    await server.call_tool(
        "append_run_event",
        {"run_id": rid, "event_type": "agent.started", "message": "hi", "agent_id": "a1", "payload": {"k": 1}},
    )
    done = (await server.call_tool("finish_run", {"run_id": rid, "status": "completed", "summary": "ok"})).structured_content
    assert done["status"] == "completed"
    events = (await server.call_tool("list_run_events", {"run_id": rid})).structured_content["result"]
    assert [e["event_type"] for e in events] == ["run.created", "agent.started", "run.completed"]
    assert events[1]["payload"] == {"k": 1}


@pytest.mark.parametrize(
    "tool,args,match",
    [
        ("get_run", {"run_id": "nope"}, "UUID"),
        ("get_run", {"run_id": str(uuid.uuid4())}, "run not found"),
        ("create_run", {"task": "x", "source": "slack"}, "source"),
        ("create_run", {"task": "   ", "source": "api"}, "task must not be empty"),
        ("finish_run", {"run_id": str(uuid.uuid4()), "status": "running"}, "status"),
    ],
)
async def test_expected_errors_are_tool_errors(server, tool, args, match):
    with pytest.raises(ToolError, match=match) as exc:
        await server.call_tool(tool, args)
    assert not isinstance(exc.value, UnexpectedToolError)  # model sees the real message, not a crash
