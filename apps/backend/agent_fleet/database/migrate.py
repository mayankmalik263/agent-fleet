"""Apply Alembic migrations. Every entry point (API, runner, MCP server) calls upgrade() at start;
it is a no-op when the schema is already at head."""

import logging
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from ..core.config import BACKEND_ROOT, get_settings
from ..core.logging import configure_logging

log = logging.getLogger(__name__)


def alembic_config(database_url: str | None = None, engine: Engine | None = None) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    cfg.attributes["skip_logging_config"] = True
    cfg.attributes["database_url"] = database_url or get_settings().database_url
    if engine is not None:
        cfg.attributes["engine"] = engine
    return cfg


def upgrade(database_url: str | None = None, engine: Engine | None = None) -> None:
    command.upgrade(alembic_config(database_url, engine), "head")
    log.debug("database schema is at head")


def main() -> None:
    """CLI: agent-fleet-db [upgrade|current]."""
    configure_logging(get_settings().log_level)
    action = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    if action == "upgrade":
        upgrade()
        log.info("database upgraded: %s", get_settings().database_url)
    elif action == "current":
        command.current(alembic_config(), verbose=True)
    else:
        sys.exit(f"unknown action {action!r}; use 'upgrade' or 'current'")
