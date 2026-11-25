"""ClaudeCodeLocalRuntime: runs one orchestration session through the user's installed, signed-in
Claude Code CLI (`claude -p --output-format stream-json --verbose`).

Local development / self-hosted connector. It does not bundle, modify or redistribute Claude Code,
does not read Claude credentials, and does not use --bare (bare mode ignores the subscription login).
"""

import asyncio
import contextlib
import logging
import time
from collections import deque

from ..core.config import Settings, get_settings
from ..core.redaction import redact_text
from ..runner import process
from ..runner.policy import policy_args
from ..runner.stream_parser import NdjsonParser, ParseIssue
from .base import ExecutionOutcome, ExecutionRequest, KeepGoing, MessageSink
from .claude_cli import child_env

log = logging.getLogger(__name__)

WATCH_INTERVAL = 2.0


def build_args(command: list[str], request: ExecutionRequest, settings: Settings) -> list[str]:
    return [
        *command,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        request.model,
        "--mcp-config",
        str(request.mcp_config_path),
        "--strict-mcp-config",
        "--agents",
        str(request.agents_path),
        "--permission-prompts",
        "none",
        # Project settings of the selected workspace are not loaded, so an untrusted repository cannot
        # add hooks or permission rules to an unattended run. The user's own settings still apply.
        "--setting-sources",
        "user",
        *policy_args(request.permission_policy, settings, web_access=request.web_access),
    ]


class ClaudeCodeLocalRuntime:
    name = "claude_code_local"

    def __init__(self, command: list[str], settings: Settings | None = None, *, on_parse_issue=None):
        self.command = command
        self.settings = settings or get_settings()
        self.on_parse_issue = on_parse_issue
        self.stderr_tail: deque[str] = deque(maxlen=60)

    async def execute(
        self, request: ExecutionRequest, on_message: MessageSink, keep_going: KeepGoing
    ) -> ExecutionOutcome:
        args = build_args(self.command, request, self.settings)
        env = child_env(self.settings)
        env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] = str(request.max_concurrent_agents)
        # Subagents must run in the foreground. A background subagent returns at once ("Async agent
        # launched"), so the orchestrator cannot wait for its result and the dashboard cannot see its end.
        env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] = "1"
        proc = await process.start(args, cwd=request.cwd, env=env)
        log.info("Claude Code started (pid %s) for run %s", proc.pid, request.run_id)

        try:
            return await self._supervise(proc, request, on_message, keep_going)
        except BaseException:
            # Runner shutdown or an unexpected error: never leave Claude Code running unattended.
            log.warning("stopping Claude Code for run %s (runner interrupted)", request.run_id)
            await asyncio.shield(process.kill_tree(proc))
            raise

    async def _supervise(
        self,
        proc: asyncio.subprocess.Process,
        request: ExecutionRequest,
        on_message: MessageSink,
        keep_going: KeepGoing,
    ) -> ExecutionOutcome:
        assert proc.stdin and proc.stdout and proc.stderr
        try:
            proc.stdin.write(request.prompt.encode("utf-8"))
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            proc.stdin.close()

        result: dict | None = None
        session_id: str | None = None

        async def read_stdout() -> None:
            nonlocal result, session_id
            parser = NdjsonParser()
            assert proc.stdout
            while True:
                chunk = await proc.stdout.read(65_536)
                items = parser.feed(chunk) if chunk else parser.flush()
                for item in items:
                    if isinstance(item, ParseIssue):
                        if self.on_parse_issue:
                            self.on_parse_issue(item.reason)
                        continue
                    if item.get("type") == "system" and item.get("subtype") == "init":
                        session_id = item.get("session_id") or session_id
                    if item.get("type") == "result":
                        result = item
                    await on_message(item)
                if not chunk:
                    return

        async def read_stderr() -> None:
            # Chunked reads: a very long stderr line must not stop the reader (readline() has a 64 KiB limit),
            # because a stopped reader would also stop the timeout and cancel checks below.
            assert proc.stderr
            pending = b""
            while chunk := await proc.stderr.read(65_536):
                *lines, pending = (pending + chunk).split(b"\n")
                pending = pending[-8_192:]
                for line in lines:
                    self.stderr_tail.append(redact_text(line.decode("utf-8", "replace").rstrip(), 500))
            if pending:
                self.stderr_tail.append(redact_text(pending.decode("utf-8", "replace").rstrip(), 500))

        readers = asyncio.gather(read_stdout(), read_stderr())
        deadline = time.monotonic() + request.timeout_seconds
        timed_out = cancelled = False
        try:
            # Watch the process itself, not only the readers: the checks must run until the process ends.
            while proc.returncode is None or not readers.done():
                done, _ = await asyncio.wait({readers}, timeout=WATCH_INTERVAL)
                if done and proc.returncode is not None:
                    break
                if done and readers.exception() is not None:
                    log.warning("output reader for run %s stopped: %s", request.run_id, readers.exception())
                if time.monotonic() > deadline:
                    timed_out = True
                elif not await keep_going():
                    cancelled = True
                if timed_out or cancelled:
                    log.warning(
                        "stopping Claude Code for run %s (%s)", request.run_id, "timeout" if timed_out else "cancelled"
                    )
                    await process.kill_tree(proc)
                    break
                if done:
                    # Readers ended but the process still runs: poll the exit without blocking the checks.
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(proc.wait(), WATCH_INTERVAL)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.shield(readers), timeout=15)
            exit_code = await proc.wait()
        finally:
            readers.cancel()

        success = (
            not timed_out
            and not cancelled
            and exit_code == 0
            and result is not None
            and not result.get("is_error")
            and result.get("subtype") == "success"
        )
        result_text = result.get("result") if result and isinstance(result.get("result"), str) else None
        return ExecutionOutcome(
            exit_code=exit_code,
            success=success,
            session_id=session_id,
            result_text=result_text,
            error=None if success else self._error_text(exit_code, result, timed_out, cancelled, request),
            timed_out=timed_out,
            cancelled=cancelled,
            usage=result.get("usage") if result and isinstance(result.get("usage"), dict) else None,
        )

    def _error_text(
        self, exit_code: int | None, result: dict | None, timed_out: bool, cancelled: bool, request: ExecutionRequest
    ) -> str:
        if timed_out:
            return f"Claude Code did not finish within {request.timeout_seconds} seconds and was stopped."
        if cancelled:
            return "The run was cancelled; Claude Code was stopped."
        if result is not None:
            subtype = result.get("subtype")
            text = result.get("result") if isinstance(result.get("result"), str) else ""
            return redact_text(f"Claude Code ended with '{subtype}'. {text}".strip(), 2_000)
        tail = " | ".join(list(self.stderr_tail)[-8:])
        return redact_text(f"Claude Code exited with code {exit_code} without a result. {tail}".strip(), 2_000)
