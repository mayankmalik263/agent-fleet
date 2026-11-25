"""Logging setup. All diagnostics go to stderr so stdout stays free for the MCP stdio protocol."""

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(getattr(h, "_agent_fleet", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler._agent_fleet = True  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level.upper())
