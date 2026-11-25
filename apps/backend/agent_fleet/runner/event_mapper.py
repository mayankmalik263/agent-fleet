"""Map Claude Code stream-json messages to Agent Fleet records.

What is recorded (public, structured data only):
- system/init            -> execution.session_started, run.session_id, run status planning -> running
- system/api_retry       -> execution.notice (error category, attempt)
- system/permission_denied -> tool.failed with denied=true
- assistant text         -> agent message (public output of that agent)
- assistant tool_use     -> tool.started; the Agent/Task tool is a delegation that creates or links a subagent
- user tool_result       -> tool.completed / tool.failed; for a delegation the subagent is completed / failed
                           and its final answer becomes a result message. "Async agent launched" (a background
                           subagent) is not an end: the agent keeps running until it reports or the run ends.
- result                 -> execution.usage_reported (cost is a client-side estimate), permission denials
Thinking blocks are never read or stored. Unknown message types are counted and ignored, so a newer
Claude Code version with extra message types does not break the run.

The subagent of a delegation is found by `parent_tool_use_id` on its messages, which carries the id of
the Agent tool_use block that started it (documented stream behaviour). Nesting works the same way.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ..core.enums import AgentStatus, EventSource, EventType, MessageType, RunStatus
from ..core.redaction import redact_text, sanitize
from ..core.state_machine import AGENT_TERMINAL, RUN_TERMINAL
from ..database import session_scope
from ..models import Agent, Run
from ..repositories import scoped
from ..services.agents import AgentService, safe_name
from ..services.events import EventService
from ..services.messages import MessageService
from ..services.runs import RunService

log = logging.getLogger(__name__)

DELEGATION_TOOLS = {"Agent", "Task"}
AGENT_ID_MARKER = re.compile(r"AGENT_FLEET_AGENT_ID:\s*([0-9a-fA-F-]{36})")
TASK_ID_MARKER = re.compile(r"AGENT_FLEET_TASK_ID:\s*([0-9a-fA-F-]{36})")
ASYNC_LAUNCH_PREFIX = "Async agent launched"
# The final answer of a subagent is its report to the orchestrator; keep enough of it to read in the UI.
SUBAGENT_RESULT_CHARS = 8_000
AUTH_ERRORS = {"authentication_failed", "oauth_org_not_allowed", "account_on_hold"}
QUIET_SYSTEM_SUBTYPES = {
    "hook_started",
    "hook_progress",
    "hook_response",
    "plugin_install",
    "status",
    "compact_boundary",
}


@dataclass
class StreamState:
    session_id: str | None = None
    result: dict[str, Any] | None = None
    api_errors: list[str] = field(default_factory=list)
    parse_issues: int = 0
    unknown_types: dict[str, int] = field(default_factory=dict)
    mcp_status: str | None = None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _summarize_input(tool: str, data: Any) -> str:
    """A short, safe description of what a tool was asked to do (never the full input)."""
    if not isinstance(data, dict):
        return ""
    for key in ("file_path", "path", "pattern", "url", "query", "command", "description", "subagent_type"):
        if key in data and isinstance(data[key], str):
            return redact_text(f"{key}={data[key]}", 300)
    keys = ", ".join(sorted(str(k) for k in list(data)[:8]))
    return f"arguments: {keys}" if keys else ""


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        return "\n".join(t for t in texts if isinstance(t, str))
    return ""


def _result_preview(content: Any, limit: int = 500) -> str:
    text = _result_text(content)
    return redact_text(text, limit) if text else ""


_HANDBACK_TAGS = re.compile(r"<(tools-used-before-summary|usage)>.*?</\1>", re.DOTALL)
_HANDBACK_START = "[Subagent hand-back]"
_HANDBACK_BODY = "The report follows:"
_TRAILING_AGENT_ID = re.compile(r"\n\s*agentId:\s*\S+\s*$")


def clean_subagent_result(text: str) -> str:
    """Keep only the subagent's own report from a delegation tool result.

    Claude Code wraps the report in harness metadata (tools used, a hand-back notice, the internal agent
    id, token usage) and indents each line by two spaces. None of that is the agent's message.
    """
    text = _HANDBACK_TAGS.sub("", text)
    start = text.find(_HANDBACK_START)
    if start != -1:
        body = text.find(_HANDBACK_BODY, start)
        if body != -1:
            text = text[body + len(_HANDBACK_BODY) :]
            text = "\n".join(line[2:] if line.startswith("  ") else line for line in text.split("\n"))
    text = _TRAILING_AGENT_ID.sub("", text.rstrip())
    return text.strip()


def _is_async_launch(content: Any) -> bool:
    """True for the immediate tool result of a background subagent (it carries no work result)."""
    return _result_text(content).lstrip().startswith(ASYNC_LAUNCH_PREFIX)


class StreamMapper:
    def __init__(
        self,
        factory: sessionmaker[Session] | None,
        workspace_id: str,
        run_id: str,
        root_agent_id: str,
        agent_models: dict[str, str] | None = None,
    ):
        self.factory = factory
        self.workspace_id = workspace_id
        self.run_id = run_id
        self.root_agent_id = root_agent_id
        self.agent_models = agent_models or {}
        self.state = StreamState()
        self.tool_uses: dict[str, tuple[str, str]] = {}  # tool_use_id -> (tool name, agent id)
        self.delegations: dict[str, str] = {}  # Agent tool_use_id -> subagent agent id
        self.usage: dict[str, dict[str, tuple[int, int]]] = {}  # agent id -> message id -> (input, output)

    # ------------------------------------------------------------------ entry point
    def handle(self, message: dict[str, Any]) -> None:
        """Process one stream message in its own transaction. Never raises for odd input."""
        kind = message.get("type")
        try:
            with session_scope(self.factory) as session:
                run = session.get(Run, self.run_id)
                if run is None:
                    return
                if kind == "system":
                    self._system(session, run, message)
                elif kind == "assistant":
                    self._assistant(session, run, message)
                elif kind == "user":
                    self._user(session, run, message)
                elif kind == "result":
                    self._result(session, run, message)
                elif kind in ("stream_event", "rate_limit_event", "prompt_suggestion"):
                    return
                else:
                    key = str(kind)[:40]
                    self.state.unknown_types[key] = self.state.unknown_types.get(key, 0) + 1
        except Exception:  # one bad message must not stop the run
            log.exception("could not record stream message of type %s", kind)

    def note_parse_issue(self, reason: str) -> None:
        self.state.parse_issues += 1
        log.warning("stream-json line skipped: %s", reason)

    # ------------------------------------------------------------------ helpers
    def _events(self, session: Session) -> EventService:
        return EventService(session)

    def _owner(self, message: dict[str, Any]) -> str:
        parent = message.get("parent_tool_use_id")
        return self.delegations.get(parent, self.root_agent_id) if isinstance(parent, str) else self.root_agent_id

    # ------------------------------------------------------------------ system
    def _system(self, session: Session, run: Run, message: dict[str, Any]) -> None:
        subtype = message.get("subtype")
        events = self._events(session)
        if subtype == "init":
            session_id = message.get("session_id")
            if isinstance(session_id, str):
                self.state.session_id = session_id
                run.session_id = session_id[:64]
            servers = [
                {"name": str(s.get("name"))[:80], "status": str(s.get("status"))[:40]}
                for s in message.get("mcp_servers", [])
                if isinstance(s, dict)
            ]
            ours = next((s for s in servers if s["name"] == "agent-fleet"), None)
            self.state.mcp_status = ours["status"] if ours else "missing"
            events.emit(
                run,
                EventType.EXECUTION_SESSION_STARTED,
                "Claude Code session started",
                source=EventSource.RUNNER,
                agent_id=self.root_agent_id,
                idempotency_key=f"stream:init:{session_id}",
                payload={
                    "model": message.get("model"),
                    "permission_mode": message.get("permissionMode"),
                    "claude_code_version": message.get("claude_code_version"),
                    "tool_count": len(message.get("tools", []) or []),
                    "mcp_servers": servers,
                    "agents": message.get("agents"),
                },
            )
            if self.state.mcp_status not in ("connected", None):
                events.emit(
                    run,
                    EventType.EXECUTION_NOTICE,
                    f"Agent Fleet MCP server status in Claude Code: {self.state.mcp_status}",
                    source=EventSource.RUNNER,
                    payload={"mcp_servers": servers},
                )
            if run.status == RunStatus.PLANNING:
                RunService(session, self.workspace_id, EventSource.RUNNER).transition(
                    run, RunStatus.RUNNING, "Claude Code session is running"
                )
        elif subtype == "api_retry":
            error = str(message.get("error") or "unknown")[:60]
            self.state.api_errors.append(error)
            events.emit(
                run,
                EventType.EXECUTION_NOTICE,
                f"Claude API retry {message.get('attempt')}: {error}",
                source=EventSource.RUNNER,
                agent_id=self.root_agent_id,
                idempotency_key=f"stream:retry:{message.get('uuid')}" if message.get("uuid") else None,
                payload={
                    k: message.get(k) for k in ("attempt", "max_retries", "retry_delay_ms", "error_status", "error")
                },
            )
        elif subtype == "permission_denied":
            tool = str(message.get("tool_name") or message.get("tool") or "tool")[:80]
            tool_use_id = message.get("tool_use_id")
            owner = (
                self.tool_uses.get(tool_use_id, (tool, self._owner(message)))[1]
                if isinstance(tool_use_id, str)
                else self._owner(message)
            )
            events.emit(
                run,
                EventType.TOOL_FAILED,
                f"Permission denied: {tool}",
                source=EventSource.RUNNER,
                agent_id=owner,
                payload={"tool_name": tool, "tool_use_id": tool_use_id, "denied": True},
                idempotency_key=f"stream:denied:{tool_use_id}" if tool_use_id else None,
            )
        elif subtype not in QUIET_SYSTEM_SUBTYPES:
            key = f"system/{str(subtype)[:30]}"
            self.state.unknown_types[key] = self.state.unknown_types.get(key, 0) + 1

    # ------------------------------------------------------------------ assistant
    def _assistant(self, session: Session, run: Run, message: dict[str, Any]) -> None:
        body = _dict(message.get("message"))
        owner_id = self._owner(message)
        owner = session.get(Agent, owner_id)
        self._record_usage(session, owner, body)
        for block in body.get("content", []) or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and owner is not None and isinstance(block.get("text"), str) and block["text"].strip():
                if run.status in RUN_TERMINAL:
                    continue
                digest = hashlib.sha1(block["text"].encode(), usedforsecurity=False).hexdigest()[:12]
                MessageService(session, self.workspace_id, EventSource.RUNNER).send(
                    run.id,
                    owner.id,
                    redact_text(block["text"], 4_000),
                    message_type=MessageType.NOTE,
                    idempotency_key=f"stream:text:{body.get('id')}:{digest}",
                )
            elif btype == "tool_use":
                self._tool_use(session, run, owner, block)
            # "thinking" and "redacted_thinking" blocks are skipped on purpose.

    def _record_usage(self, session: Session, agent: Agent | None, body: dict[str, Any]) -> None:
        usage = body.get("usage")
        msg_id = body.get("id")
        if agent is None or not isinstance(usage, dict) or not isinstance(msg_id, str):
            return

        def num(key: str) -> int:
            value = usage.get(key)
            return int(value) if isinstance(value, int | float) and value >= 0 else 0

        # Input counts prompt tokens including cache reads and writes. One API message can arrive as several
        # stream messages with the same id, so the latest value per message id is kept, not summed.
        per_agent = self.usage.setdefault(agent.id, {})
        per_agent[msg_id] = (
            num("input_tokens") + num("cache_creation_input_tokens") + num("cache_read_input_tokens"),
            num("output_tokens"),
        )
        agent.input_tokens = sum(v[0] for v in per_agent.values())
        agent.output_tokens = sum(v[1] for v in per_agent.values())

    def _tool_use(self, session: Session, run: Run, owner: Agent | None, block: dict[str, Any]) -> None:
        tool_use_id = block.get("id")
        name = str(block.get("name") or "tool")[:120]
        if not isinstance(tool_use_id, str) or owner is None:
            return
        data = _dict(block.get("input"))
        self.tool_uses[tool_use_id] = (name, owner.id)
        owner.tool_call_count = (owner.tool_call_count or 0) + 1
        events = self._events(session)
        events.emit(
            run,
            EventType.TOOL_STARTED,
            f"{owner.name} called {name}",
            source=EventSource.RUNNER,
            agent_id=owner.id,
            parent_agent_id=owner.parent_agent_id,
            payload={"tool_name": name, "tool_use_id": tool_use_id, "input_summary": _summarize_input(name, data)},
            idempotency_key=f"stream:tool:{tool_use_id}:start",
        )
        if name in DELEGATION_TOOLS and run.status not in RUN_TERMINAL:
            self._delegate(session, run, owner, tool_use_id, data)

    def _delegate(self, session: Session, run: Run, owner: Agent, tool_use_id: str, data: dict[str, Any]) -> None:
        agents = AgentService(session, self.workspace_id, EventSource.RUNNER)
        prompt = _str(data.get("prompt"))
        subagent_type = safe_name(
            data.get("subagent_type") if isinstance(data.get("subagent_type"), str) else None, "general-purpose"
        )
        marker = AGENT_ID_MARKER.search(prompt)
        agent: Agent | None = None
        if marker:
            try:
                agent = scoped.get_agent(session, self.workspace_id, marker.group(1), run.id)
            except Exception:
                agent = None
        if agent is not None:
            if agent.external_ref is None:
                agent.external_ref = f"tool:{tool_use_id}"
            if agent.status not in AGENT_TERMINAL and agent.status != AgentStatus.RUNNING:
                agents.update_status(
                    run.id,
                    agent.id,
                    AgentStatus.RUNNING,
                    message=f"{agent.name} started (delegated by {owner.name})",
                    idempotency_key=f"stream:tool:{tool_use_id}:agent-start",
                )
        else:
            model = _str(data.get("model")) or self.agent_models.get(subagent_type, "inherit")
            agent = agents.register(
                run.id,
                subagent_type,
                subagent_type,
                model,
                owner.id,
                status=AgentStatus.RUNNING,
                external_ref=f"tool:{tool_use_id}",
                enforce_capacity=False,
                idempotency_key=f"stream:tool:{tool_use_id}:agent",
            )
        self.delegations[tool_use_id] = agent.id
        description = _str(data.get("description"))
        task_marker = TASK_ID_MARKER.search(prompt)
        task_id = task_marker.group(1) if task_marker else None
        try:
            if task_id:
                scoped.get_task(session, self.workspace_id, task_id, run.id)
        except Exception:
            task_id = None
        MessageService(session, self.workspace_id, EventSource.RUNNER).send(
            run.id,
            owner.id,
            f"Delegated: {description or subagent_type}\n\n{redact_text(prompt, 1_500)}",
            message_type=MessageType.INSTRUCTION,
            receiver_agent_id=agent.id,
            task_id=task_id,
            idempotency_key=f"stream:tool:{tool_use_id}:instruction",
        )

    # ------------------------------------------------------------------ user (tool results)
    def _user(self, session: Session, run: Run, message: dict[str, Any]) -> None:
        body = _dict(message.get("message"))
        content = body.get("content")
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_use_id = block.get("tool_use_id")
            if not isinstance(tool_use_id, str):
                continue
            name, agent_id = self.tool_uses.get(tool_use_id, ("tool", self._owner(message)))
            failed = bool(block.get("is_error"))
            preview = _result_preview(block.get("content"))
            agent = session.get(Agent, agent_id)
            self._events(session).emit(
                run,
                EventType.TOOL_FAILED if failed else EventType.TOOL_COMPLETED,
                f"{name} {'failed' if failed else 'returned'}" + (f" for {agent.name}" if agent else ""),
                source=EventSource.RUNNER,
                agent_id=agent_id,
                parent_agent_id=agent.parent_agent_id if agent else None,
                payload={"tool_name": name, "tool_use_id": tool_use_id, "is_error": failed, "output_preview": preview},
                idempotency_key=f"stream:tool:{tool_use_id}:end",
            )
            sub_id = self.delegations.get(tool_use_id)
            if sub_id and run.status not in RUN_TERMINAL:
                sub = session.get(Agent, sub_id)
                if not failed and _is_async_launch(block.get("content")):
                    # A background subagent: the tool returned before the work. The agent keeps running;
                    # it reports its own end with MCP, or the run closes it.
                    continue
                report = clean_subagent_result(_result_text(block.get("content")))
                full = redact_text(report, SUBAGENT_RESULT_CHARS) if report else ""
                if sub is not None and sub.status not in AGENT_TERMINAL:
                    AgentService(session, self.workspace_id, EventSource.RUNNER).update_status(
                        run.id,
                        sub.id,
                        AgentStatus.FAILED if failed else AgentStatus.COMPLETED,
                        message=f"{sub.name} {'failed' if failed else 'finished'}",
                        idempotency_key=f"stream:tool:{tool_use_id}:agent-end",
                    )
                if sub is not None and full:
                    MessageService(session, self.workspace_id, EventSource.RUNNER).send(
                        run.id,
                        sub.id,
                        full,
                        message_type=MessageType.RESULT,
                        receiver_agent_id=agent_id,
                        idempotency_key=f"stream:tool:{tool_use_id}:result",
                    )

    # ------------------------------------------------------------------ result
    def _result(self, session: Session, run: Run, message: dict[str, Any]) -> None:
        self.state.result = message
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else None
        cost = message.get("total_cost_usd")
        report = {
            "usage": sanitize(usage) if usage else None,
            "num_turns": message.get("num_turns"),
            "duration_ms": message.get("duration_ms"),
            "duration_api_ms": message.get("duration_api_ms"),
            "estimated_cost_usd": cost if isinstance(cost, int | float) else None,
            "cost_is_estimate": True,
            "cost_note": "Client-side estimate from Claude Code. Not an invoice.",
            "model_usage": sanitize(message.get("modelUsage")) if isinstance(message.get("modelUsage"), dict) else None,
            "subtype": message.get("subtype"),
        }
        run.usage_json = report
        events = self._events(session)
        events.emit(
            run,
            EventType.EXECUTION_USAGE_REPORTED,
            "Claude Code reported usage",
            source=EventSource.RUNNER,
            agent_id=self.root_agent_id,
            payload=report,
            idempotency_key=f"stream:result:{message.get('uuid') or message.get('session_id')}:{message.get('num_turns')}",  # noqa: E501
        )
        for denial in message.get("permission_denials", []) or []:
            if not isinstance(denial, dict):
                continue
            tool_use_id = denial.get("tool_use_id")
            tool = str(denial.get("tool_name") or "tool")[:80]
            owner = (
                self.tool_uses.get(tool_use_id, (tool, self.root_agent_id))[1]
                if isinstance(tool_use_id, str)
                else self.root_agent_id
            )
            events.emit(
                run,
                EventType.TOOL_FAILED,
                f"Permission denied: {tool}",
                source=EventSource.RUNNER,
                agent_id=owner,
                payload={"tool_name": tool, "tool_use_id": tool_use_id, "denied": True},
                idempotency_key=f"stream:denied:{tool_use_id}" if tool_use_id else None,
            )
