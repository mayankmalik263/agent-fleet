"""Start and stop the Claude Code process tree. Argument arrays only; never shell=True."""

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path


async def start(args: list[str], *, cwd: Path, env: dict[str, str]) -> asyncio.subprocess.Process:
    kwargs: dict[str, object] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **kwargs,  # type: ignore[arg-type]
    )


async def kill_tree(proc: asyncio.subprocess.Process, grace_seconds: float = 5.0) -> None:
    """Stop the process and its children (Claude Code starts MCP servers and tool processes)."""
    if proc.returncode is not None:
        return
    try:
        if sys.platform == "win32":
            # taskkill /T stops the whole tree; /F because console programs ignore a polite close.
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(proc.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(proc.wait(), grace_seconds)
            except TimeoutError:
                os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        await asyncio.wait_for(proc.wait(), grace_seconds)
    except TimeoutError:
        proc.kill()
