"""Optional Graphify connector (https://github.com/Graphify-Labs/graphify).

Graphify builds a local code knowledge graph in <workspace>/graphify-out/graph.json. Agent Fleet only
detects the CLI and the graph and runs read-only `graphify query|path|explain` commands on request.
It never installs Graphify, never uploads code, and never parses code itself. The Graphify code graph
and the Agent Fleet agent graph are separate things.
"""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..providers.claude_cli import child_env

QUERY_COMMANDS = ("query", "path", "explain")
# Documented exit codes: 0 answer, 3 ambiguous name, 4 no match.
EXIT_MEANING = {0: "answer", 3: "ambiguous", 4: "no_match"}


@dataclass
class GraphifyStatus:
    installed: bool
    executable: str | None
    graph_path: str | None
    graph_present: bool
    message: str
    details: dict[str, str] = field(default_factory=dict)


def find_cli() -> str | None:
    return shutil.which("graphify")


def status(workspace: Path | None) -> GraphifyStatus:
    exe = find_cli()
    graph = (workspace / "graphify-out" / "graph.json") if workspace else None
    present = bool(graph and graph.is_file())
    if exe is None:
        msg = "Graphify is not installed (optional). See docs/GRAPHIFY_INTEGRATION.md."
    elif not present:
        msg = "Graphify is installed. No graph yet: run `/graphify .` in Claude Code inside the workspace."
    else:
        msg = "Graphify is installed and a local graph is available."
    return GraphifyStatus(
        installed=exe is not None,
        executable=exe,
        graph_path=str(graph) if graph else None,
        graph_present=present,
        message=msg,
    )


def run_query(workspace: Path, command: str, args: list[str], timeout: float = 60.0) -> dict[str, object]:
    """Run a read-only Graphify query in the workspace. Raises RuntimeError when unavailable."""
    if command not in QUERY_COMMANDS:
        raise ValueError(f"command must be one of {QUERY_COMMANDS}")
    if not args or any(not isinstance(a, str) or not a.strip() or len(a) > 500 or a.startswith("-") for a in args):
        raise ValueError("arguments must be 1-2 non-empty strings (max 500 characters, not starting with '-')")
    st = status(workspace)
    if not st.installed or st.executable is None:
        raise RuntimeError(st.message)
    if not st.graph_present:
        raise RuntimeError(st.message)
    if Path(st.executable).suffix.lower() in (".cmd", ".bat"):
        # Batch shims pass arguments through cmd.exe; refuse rather than risk argument injection.
        raise RuntimeError("Graphify resolved to a .cmd/.bat shim; install it with `uv tool install graphifyy`.")
    proc = subprocess.run(  # noqa: S603 - argument array, no shell; option-like arguments are rejected above
        [st.executable, command, *args[:2]],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=child_env(),
        stdin=subprocess.DEVNULL,
        check=False,
    )
    return {
        "exit_code": proc.returncode,
        "outcome": EXIT_MEANING.get(proc.returncode, "error"),
        "output": proc.stdout[-20_000:],
        "error": proc.stderr[-2_000:] if proc.returncode not in EXIT_MEANING else "",
    }
