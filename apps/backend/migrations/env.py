from logging.config import fileConfig

from alembic import context

from agent_fleet import models  # noqa: F401  (registers all tables on Base.metadata)
from agent_fleet.core.config import get_settings
from agent_fleet.database import Base, build_engine

config = context.config
# Programmatic upgrades (agent_fleet.database.migrate) set this attribute to keep our own logging setup.
if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return config.attributes.get("database_url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = config.attributes.get("engine") or build_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
