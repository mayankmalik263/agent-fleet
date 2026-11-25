"""Detect the installed Claude Code CLI through its documented commands only:
`claude --version`, `claude auth status --json` and `claude --help`.
Agent Fleet never reads Claude credential files, tokens or cookies."""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import Settings, get_settings

log = logging.getLogger(__name__)

# Flags the runtime uses. Each one is checked against `claude --help` of the installed binary.
REQUIRED_FLAGS = (
    "--print",
    "--output-format",
    "--verbose",
    "--model",
    "--mcp-config",
    "--strict-mcp-config",
    "--permission-mode",
    "--allowedTools",
    "--disallowedTools",
    "--agents",
    "--tools",
    "--permission-prompts",
    "--setting-sources",
)
# Environment variables that would switch Claude Code from the subscription login to API billing.
API_CREDENTIAL_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_SAFE_AUTH_FIELDS = ("loggedIn", "authMethod", "apiProvider", "subscriptionType")


@dataclass
class ClaudeInstallation:
    found: bool
    executable: str | None = None
    version: str | None = None
    logged_in: bool = False
    auth: dict[str, object] = field(default_factory=dict)
    missing_flags: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.found and self.logged_in and not self.missing_flags and not self.problems


def child_env(settings: Settings | None = None) -> dict[str, str]:
    """Environment for Claude Code child processes. API keys are removed so local runs use the
    official subscription login, unless AGENT_FLEET_KEEP_API_KEY_ENV=true."""
    settings = settings or get_settings()
    env = dict(os.environ)
    if not settings.keep_api_key_env:
        for name in API_CREDENTIAL_ENV:
            env.pop(name, None)
    # Make sure the child never inherits a request to bypass permissions.
    env.pop("CLAUDE_CODE_DANGEROUSLY_SKIP_PERMISSIONS", None)
    return env


def find_executable(settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    if settings.claude_path:
        path = Path(settings.claude_path).expanduser()
        return str(path) if path.is_file() else None
    found = shutil.which("claude")
    if found and sys.platform == "win32" and Path(found).suffix.lower() in (".cmd", ".bat", ".ps1", ""):
        # npm installs a .cmd shim. Running .cmd files sends arguments through cmd.exe, which is unsafe
        # for arbitrary prompt text, so use the native binary that the shim starts.
        shim_dir = Path(found).parent
        native = shim_dir / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if native.is_file():
            return str(native)
        exe = shutil.which("claude.exe")
        return exe
    if found:
        return found
    home_native = Path.home() / ".local" / "bin" / ("claude.exe" if sys.platform == "win32" else "claude")
    return str(home_native) if home_native.is_file() else None


def _run(args: list[str], timeout: float, settings: Settings) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argument array, no shell
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=child_env(settings),
        stdin=subprocess.DEVNULL,
        check=False,
    )


def detect(settings: Settings | None = None) -> ClaudeInstallation:
    settings = settings or get_settings()
    exe = find_executable(settings)
    if exe is None:
        return ClaudeInstallation(
            found=False,
            problems=[
                "Claude Code was not found. Install it from https://code.claude.com/docs/en/setup, "
                "or set AGENT_FLEET_CLAUDE_PATH to the claude executable."
            ],
        )
    info = ClaudeInstallation(found=True, executable=exe)
    timeout = settings.claude_detect_timeout_seconds
    try:
        version = _run([exe, "--version"], timeout, settings)
        match = re.search(r"\d+\.\d+\.\d+", version.stdout)
        info.version = match.group(0) if match else version.stdout.strip()[:40] or None

        helptext = _run([exe, "--help"], timeout, settings).stdout
        info.missing_flags = [flag for flag in REQUIRED_FLAGS if flag not in helptext]
        if info.missing_flags:
            info.problems.append(
                "This Claude Code version lacks options Agent Fleet needs: "
                + ", ".join(info.missing_flags)
                + ". Run `claude update`."
            )

        auth = _run([exe, "auth", "status", "--json"], timeout, settings)
        try:
            data = json.loads(auth.stdout or "{}")
        except json.JSONDecodeError:
            data = {}
        # Keep only non-identifying fields. Email, organisation and account ids are dropped.
        info.auth = {k: data[k] for k in _SAFE_AUTH_FIELDS if k in data}
        info.logged_in = bool(data.get("loggedIn"))
        if not info.logged_in:
            info.problems.append("Claude Code is not signed in. Run `claude auth login` (or `claude` then /login).")
    except subprocess.TimeoutExpired:
        info.problems.append("Claude Code did not answer in time during detection.")
    except OSError as exc:
        info.problems.append(f"Claude Code could not be started: {exc.strerror or exc}")
    return info


class _Cache:
    def __init__(self, ttl: float = 60.0):
        self.ttl = ttl
        self.lock = threading.Lock()
        self.value: ClaudeInstallation | None = None
        self.at = 0.0

    def get(self, refresh: bool = False) -> ClaudeInstallation:
        with self.lock:
            if refresh or self.value is None or time.monotonic() - self.at > self.ttl:
                self.value = detect()
                self.at = time.monotonic()
            return self.value


_cache = _Cache()


def cached_detect(refresh: bool = False) -> ClaudeInstallation:
    return _cache.get(refresh)
