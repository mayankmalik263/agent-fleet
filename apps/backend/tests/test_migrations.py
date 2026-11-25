"""Regression: migration 0002 rebuilt the runs table with foreign keys on, and the DROP of the old table
cascade-deleted all agents, tasks, messages and events (2026-11-25). Upgrades must keep existing data."""

from pathlib import Path

from alembic import command
from sqlalchemy import text

from agent_fleet.core.enums import EventSource
from agent_fleet.database import build_engine, get_session_factory, session_scope
from agent_fleet.database.migrate import alembic_config
from agent_fleet.services.agents import AgentService
from agent_fleet.services.runs import RunService
from agent_fleet.services.tasks import TaskService


def test_upgrade_from_0001_keeps_child_rows(tmp_path: Path, monkeypatch, workspace_id):
    url = f"sqlite:///{(tmp_path / 'old.sqlite3').as_posix()}"
    engine = build_engine(url)
    command.upgrade(alembic_config(url, engine), "0001")

    factory = get_session_factory(engine)
    with session_scope(factory) as s:
        # Raw insert: the 0001 schema has no web_access column, so the ORM cannot write a run here.
        s.execute(
            text(
                "INSERT INTO runs (id, workspace_id, title, task_description, source, execution_mode, provider,"
                " status, permission_policy, orchestrator_model, max_concurrent_agents, created_at, updated_at,"
                " attempt_count, cancel_requested, event_seq) VALUES ('11111111-1111-4111-8111-111111111111',"
                " :ws, 't', 'd', 'claude_code', 'local_claude_code', 'claude_code_local', 'running', 'read_only',"
                " 'sonnet', 4, '2026-11-25 00:00:00', '2026-11-25 00:00:00', 0, 0, 0)"
            ),
            {"ws": workspace_id},
        )
    command.upgrade(alembic_config(url, engine), "head")

    run_id = "11111111-1111-4111-8111-111111111111"
    with session_scope(factory) as s:
        agents = AgentService(s, workspace_id, EventSource.MCP)
        root = agents.register(run_id, "orchestrator", "orchestrator", "sonnet")
        TaskService(s, workspace_id, EventSource.MCP).create(run_id, "T", "D", root.id)
    with engine.connect() as c:
        before = {t: c.exec_driver_sql(f"select count(*) from {t}").scalar() for t in ("agents", "tasks", "run_events")}

    # Downgrade and upgrade again: both rebuild the runs table.
    command.downgrade(alembic_config(url, engine), "0001")
    command.upgrade(alembic_config(url, engine), "head")
    with engine.connect() as c:
        after = {t: c.exec_driver_sql(f"select count(*) from {t}").scalar() for t in ("agents", "tasks", "run_events")}
        assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1  # checks are back on for the pool
        root_id = c.exec_driver_sql(f"select root_agent_id from runs where id='{run_id}'").scalar()
    assert before == after and after["agents"] == 1 and after["tasks"] == 1
    assert root_id == root.id
    with session_scope(factory) as s:
        assert RunService(s, workspace_id, EventSource.API).snapshot(run_id)["agents"]
    engine.dispose()
