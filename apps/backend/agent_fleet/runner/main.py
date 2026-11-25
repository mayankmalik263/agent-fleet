"""Entry point: agent-fleet-runner."""

import asyncio
import contextlib
import logging

from ..core.config import get_settings
from ..core.logging import configure_logging
from ..database.migrate import upgrade
from .worker import Runner

log = logging.getLogger("agent_fleet.runner")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    upgrade()
    log.info("Agent Fleet local runner (local development / self-hosted Claude Code connector)")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(Runner(settings).run_forever())
