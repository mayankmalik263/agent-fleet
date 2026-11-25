"""Claude Code hook relay (entry point: agent-fleet-hook). Used by .claude/settings.json in this repository.

- SessionStart: prints additionalContext with the session id, so Claude can pass it to create_run.
- SubagentStart, SubagentStop, PostToolUseFailure, SessionEnd: sends ids and names (never tool inputs or
  outputs) to the local API, which attaches them to the run that has this session id.
The relay never blocks Claude Code: it always exits 0, uses a short timeout, and ignores every error.
"""

import json
import sys
import urllib.error
import urllib.request

from ..core.config import get_settings

FORWARD_EVENTS = {"SubagentStart", "SubagentStop", "PostToolUseFailure", "SessionEnd"}
FORWARD_FIELDS = ("hook_event_name", "session_id", "agent_id", "agent_type", "tool_name", "tool_use_id", "reason")
TIMEOUT_SECONDS = 2.0


def session_start_output(session_id: str) -> str:
    context = (
        f"Agent Fleet: the Claude Code session id of this session is {session_id}. "
        "The Agent Fleet create_run tool accepts it as session_id, which lets Agent Fleet attach "
        "subagent lifecycle events from hooks to that run."
    )
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}})


def forward(data: dict[str, object], api_base_url: str) -> None:
    body = json.dumps({k: data[k] for k in FORWARD_FIELDS if k in data}).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - fixed local http URL from settings
        f"{api_base_url}/api/v1/integrations/claude-code/hooks",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):  # noqa: S310
        pass


def main() -> None:
    try:
        raw = sys.stdin.read(1_000_000)
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            return
        event = data.get("hook_event_name")
        session_id = data.get("session_id")
        if event == "SessionStart" and isinstance(session_id, str):
            sys.stdout.write(session_start_output(session_id))
        elif event in FORWARD_EVENTS:
            forward(data, get_settings().api_base_url)
    except (OSError, ValueError, urllib.error.URLError):
        pass
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
