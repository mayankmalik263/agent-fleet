"""Fake Claude Code CLI for tests. It never calls a model.

It reads the prompt from stdin and writes stream-json like `claude -p --output-format stream-json --verbose`.
Scenario comes from FAKE_CLAUDE_SCENARIO:
- e2e:        acts as a real MCP client of the Agent Fleet server in --mcp-config (registers 4 agents,
              creates tasks, sends messages, submits results, completes the run) and emits matching
              Agent tool_use / tool_result stream messages.
- no_complete: finishes successfully but never calls complete_run (runner must use the result text).
- malformed:  mixes partial writes, invalid JSON, non-object JSON and unknown message types.
- crash:      prints init, writes to stderr, exits with code 3.
- hang:       prints init, then sleeps (for timeout and cancellation tests).
- auth:       reports an authentication api_retry, then an error result.
"""

import asyncio
import json
import os
import re
import sys
import time
import uuid

ARGS = sys.argv[1:]
SCENARIO = os.environ.get("FAKE_CLAUDE_SCENARIO", "e2e")
SESSION = str(uuid.uuid4())


def arg(name: str) -> str | None:
    return ARGS[ARGS.index(name) + 1] if name in ARGS else None


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def init() -> None:
    emit(
        {
            "type": "system",
            "subtype": "init",
            "session_id": SESSION,
            "model": arg("--model"),
            "permissionMode": arg("--permission-mode"),
            "tools": ["Read", "Agent"],
            "claude_code_version": "fake",
            "mcp_servers": [{"name": "agent-fleet", "status": "connected"}],
        }
    )


def assistant(content: list, parent: str | None = None, msg_id: str | None = None, usage: dict | None = None) -> None:
    emit(
        {
            "type": "assistant",
            "parent_tool_use_id": parent,
            "session_id": SESSION,
            "message": {
                "id": msg_id or f"msg_{uuid.uuid4().hex[:8]}",
                "role": "assistant",
                "content": content,
                "usage": usage or {"input_tokens": 10, "output_tokens": 5},
            },
        }
    )


def tool_result(tool_use_id: str, text: str, parent: str | None = None, is_error: bool = False) -> None:
    emit(
        {
            "type": "user",
            "parent_tool_use_id": parent,
            "session_id": SESSION,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": [{"type": "text", "text": text}],
                        "is_error": is_error,
                    }
                ],
            },
        }
    )


def result(text: str, *, error: bool = False, subtype: str = "success") -> None:
    emit(
        {
            "type": "result",
            "subtype": subtype,
            "is_error": error,
            "result": text,
            "session_id": SESSION,
            "num_turns": 3,
            "duration_ms": 1234,
            "total_cost_usd": 0.0123,
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "permission_denials": [],
        }
    )


async def e2e(prompt: str) -> None:
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters

    run_id = re.search(r"run_id: ([0-9a-f-]{36})", prompt).group(1)
    root = re.search(r"your agent_id: ([0-9a-f-]{36})", prompt).group(1)
    server = json.load(open(arg("--mcp-config"), encoding="utf-8"))["mcpServers"]["agent-fleet"]
    params = StdioServerParameters(command=server["command"], args=server["args"], env=server["env"])
    init()
    assistant(
        [{"type": "thinking", "thinking": "SECRET REASONING"}, {"type": "text", "text": "Planning the work."}],
        msg_id="msg_root_1",
        usage={"input_tokens": 20, "output_tokens": 7},
    )
    async with Client(params) as c:

        async def call(name: str, args: dict) -> dict:
            res = await c.call_tool(name, args)
            assert not res.is_error, res.content
            return res.structured_content

        roles = [("researcher", "haiku"), ("analyst", "haiku"), ("executor", "sonnet"), ("reviewer", "sonnet")]
        work = []
        for role, model in roles:
            agent = await call(
                "register_agent",
                {"run_id": run_id, "name": role, "role": role, "model_alias": model, "parent_agent_id": root},
            )
            task = await call(
                "create_task",
                {
                    "run_id": run_id,
                    "title": f"{role} task",
                    "description": f"Do {role} work",
                    "assigned_agent_id": agent["agent_id"],
                    "created_by_agent_id": root,
                },
            )
            work.append((role, agent["agent_id"], task["task_id"], f"toolu_{role}"))
        # Delegate (Agent tool), as Claude Code would show it in the stream.
        assistant(
            [
                {
                    "type": "tool_use",
                    "id": tid,
                    "name": "Agent",
                    "input": {
                        "subagent_type": role,
                        "description": f"{role} task",
                        "prompt": (
                            f"AGENT_FLEET_RUN_ID: {run_id}\nAGENT_FLEET_AGENT_ID: {aid}\n"
                            f"AGENT_FLEET_TASK_ID: {task}\nGo."
                        ),
                    },
                }
                for role, aid, task, tid in work
            ],
            msg_id="msg_root_2",
        )
        for role, aid, task, tid in work:
            assistant(
                [{"type": "tool_use", "id": f"{tid}_read", "name": "Read", "input": {"file_path": "README.md"}}],
                parent=tid,
                msg_id=f"msg_{role}",
            )
            tool_result(f"{tid}_read", "file text", parent=tid)
            await call(
                "update_task_status",
                {"run_id": run_id, "task_id": task, "status": "in_progress", "progress_percentage": 50},
            )
            await call(
                "send_agent_message",
                {
                    "run_id": run_id,
                    "sender_agent_id": aid,
                    "receiver_agent_id": root,
                    "content": f"{role} is halfway",
                    "message_type": "status",
                    "task_id": task,
                },
            )
            await call(
                "submit_task_result",
                {
                    "run_id": run_id,
                    "task_id": task,
                    "agent_id": aid,
                    "result_summary": f"{role} result",
                    "result_payload": {"ok": True},
                },
            )
            await call("update_agent_status", {"run_id": run_id, "agent_id": aid, "status": "completed"})
            tool_result(tid, f"{role} finished")
        snapshot = await call("get_run_snapshot", {"run_id": run_id})
        assert len(snapshot["agents"]) == 5, snapshot["agents"]
        await call("complete_run", {"run_id": run_id, "final_summary": "All four agents finished."})
    # Real Claude Code needs a few seconds after complete_run before it prints the final result.
    time.sleep(float(os.environ.get("FAKE_CLAUDE_RESULT_DELAY", "0")))
    result("All four agents finished.")


async def main() -> None:
    prompt = sys.stdin.read()
    if os.environ.get("FAKE_CLAUDE_PID_FILE"):
        with open(os.environ["FAKE_CLAUDE_PID_FILE"], "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    if SCENARIO == "e2e":
        await e2e(prompt)
    elif SCENARIO == "no_complete":
        init()
        assistant([{"type": "text", "text": "Done without tools."}])
        result("Final answer from Claude Code.")
    elif SCENARIO == "malformed":
        line = json.dumps({"type": "system", "subtype": "init", "session_id": SESSION, "mcp_servers": []}) + "\n"
        sys.stdout.write(line[:15])
        sys.stdout.flush()
        time.sleep(0.2)
        sys.stdout.write(line[15:])
        sys.stdout.flush()
        sys.stdout.write("this is not json\n[1, 2, 3]\n")
        emit({"type": "brand_new_type", "x": 1})
        emit({"type": "system", "subtype": "future_subtype"})
        assistant([{"type": "tool_use", "id": "toolu_x", "name": "Grep", "input": {"pattern": "TODO"}}])
        tool_result("toolu_x", "denied", is_error=True)
        result("Finished despite noise.")
    elif SCENARIO == "crash":
        init()
        sys.stderr.write("fatal: something broke\n")
        sys.exit(3)
    elif SCENARIO == "noisy_hang":
        init()
        sys.stderr.write("x" * 70_000)  # one stderr line longer than 64 KiB, no newline
        sys.stderr.flush()
        time.sleep(120)
    elif SCENARIO == "long_result":
        init()
        result("y" * 25_000)
    elif SCENARIO == "blank_result":
        init()
        result("   ")
    elif SCENARIO == "hang":
        init()
        time.sleep(120)
    elif SCENARIO == "auth":
        init()
        emit(
            {
                "type": "system",
                "subtype": "api_retry",
                "attempt": 1,
                "max_retries": 1,
                "retry_delay_ms": 0,
                "error_status": 401,
                "error": "authentication_failed",
                "uuid": str(uuid.uuid4()),
                "session_id": SESSION,
            }
        )
        result("Invalid API key", error=True, subtype="error_during_execution")
        sys.exit(1)


asyncio.run(main())
