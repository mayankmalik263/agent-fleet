"""Small pure-logic checks: stream parser, redaction, hook relay, Graphify adapter, state machine."""

import io
import json
from pathlib import Path

import pytest

from agent_fleet.core.enums import AgentStatus, RunStatus
from agent_fleet.core.errors import InvalidTransitionError
from agent_fleet.core.redaction import REDACTED, sanitize
from agent_fleet.core.state_machine import check_agent_transition, check_run_transition
from agent_fleet.integrations import claude_hooks, graphify
from agent_fleet.runner.stream_parser import NdjsonParser, ParseIssue


def test_parser_handles_partial_lines_and_bad_input():
    p = NdjsonParser()
    assert p.feed(b'{"type": "sys') == []
    assert p.feed(b'tem"}\n{"a"') == [{"type": "system"}]
    out = p.feed(b": 1}\nnot json\n[1,2]\n\n")
    assert out[0] == {"a": 1}
    assert isinstance(out[1], ParseIssue) and "invalid JSON" in out[1].reason
    assert isinstance(out[2], ParseIssue) and "not an object" in out[2].reason
    assert p.feed(b'{"tail": true}') == []
    assert p.flush() == [{"tail": True}]
    assert p.flush() == []


def test_parser_handles_utf8_split_across_chunks():
    data = json.dumps({"t": "héllo ✓"}, ensure_ascii=False).encode() + b"\n"
    p = NdjsonParser()
    items = [*p.feed(data[:10]), *p.feed(data[10:])]
    assert items == [{"t": "héllo ✓"}]


def test_sanitize_removes_secrets_reasoning_and_bounds_size():
    data = {
        "api_key": "abc",
        "Authorization": "Bearer x",
        "access_token": "t",
        "input_tokens": 5,
        "thinking": "private",
        "note": "token sk-ant-api03-ABCDEFGHIJKLMNOP",
        "long": "x" * 5000,
        "nested": [{"password": "p", "ok": 1}],
    }
    out = sanitize(data)
    assert out["api_key"] == out["Authorization"] == out["access_token"] == REDACTED
    assert out["input_tokens"] == 5 and "thinking" not in out
    assert "sk-ant" not in out["note"] and out["long"].endswith("chars]")
    assert out["nested"] == [{"password": REDACTED, "ok": 1}]


def test_state_machine_rules():
    check_run_transition(RunStatus.QUEUED, RunStatus.PLANNING)
    with pytest.raises(InvalidTransitionError):
        check_run_transition(RunStatus.COMPLETED, RunStatus.RUNNING)
    check_agent_transition(AgentStatus.QUEUED, AgentStatus.RUNNING)
    with pytest.raises(InvalidTransitionError):
        check_agent_transition(AgentStatus.FAILED, AgentStatus.RUNNING)


def test_hook_relay_session_start_and_never_fails(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"hook_event_name": "SessionStart", "session_id": "s1"})))
    with pytest.raises(SystemExit) as exit_info:
        claude_hooks.main()
    assert exit_info.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert "s1" in out["hookSpecificOutput"]["additionalContext"]

    sent = {}
    monkeypatch.setattr(claude_hooks, "forward", lambda data, url: sent.update(data))
    event = {"hook_event_name": "SubagentStop", "session_id": "s1", "agent_id": "a", "tool_input": {"secret": 1}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    with pytest.raises(SystemExit):
        claude_hooks.main()
    assert sent["agent_id"] == "a"

    def boom(data, url):
        raise OSError("connection refused")

    monkeypatch.setattr(claude_hooks, "forward", boom)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    with pytest.raises(SystemExit) as exit_info:
        claude_hooks.main()
    assert exit_info.value.code == 0  # a backend outage never blocks Claude Code
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exit_info:
        claude_hooks.main()
    assert exit_info.value.code == 0


def test_hook_relay_forwards_only_safe_fields(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(claude_hooks.urllib.request, "urlopen", fake_urlopen)
    claude_hooks.forward(
        {
            "hook_event_name": "PostToolUseFailure",
            "session_id": "s",
            "tool_name": "Bash",
            "tool_input": {"command": "cat secrets"},
            "tool_response": "x",
        },
        "http://127.0.0.1:8420",
    )
    assert captured["url"].endswith("/api/v1/integrations/claude-code/hooks")
    assert captured["body"] == {"hook_event_name": "PostToolUseFailure", "session_id": "s", "tool_name": "Bash"}


def test_graphify_status_and_query_guards(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(graphify, "find_cli", lambda: None)
    st = graphify.status(tmp_path)
    assert not st.installed and "not installed" in st.message
    with pytest.raises(RuntimeError, match="not installed"):
        graphify.run_query(tmp_path, "query", ["what calls main?"])
    with pytest.raises(ValueError):
        graphify.run_query(tmp_path, "rm", ["x"])
    with pytest.raises(ValueError):
        graphify.run_query(tmp_path, "query", ["--output=/etc/passwd"])

    monkeypatch.setattr(graphify, "find_cli", lambda: str(tmp_path / "graphify.exe"))
    assert "No graph yet" in graphify.status(tmp_path).message
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}")
    assert graphify.status(tmp_path).graph_present
