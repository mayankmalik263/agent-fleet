import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Never let tests call a real Claude binary by accident.
os.environ["AGENT_FLEET_CLAUDE_PATH"] = str(FIXTURES / "does-not-exist")


def _clear_caches() -> None:
    from agent_fleet.core.config import get_settings
    from agent_fleet.database import engine as engine_mod

    get_settings.cache_clear()
    engine_mod.get_engine.cache_clear()
    engine_mod._session_factory.cache_clear()


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}"
    monkeypatch.setenv("AGENT_FLEET_DATABASE_URL", url)
    monkeypatch.setenv("AGENT_FLEET_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AGENT_FLEET_ALLOWED_WORKSPACE_ROOTS", str(tmp_path / "workspaces"))
    (tmp_path / "workspaces").mkdir()
    (tmp_path / "data" / "workspaces").mkdir(parents=True)
    _clear_caches()
    from agent_fleet.database.migrate import upgrade

    upgrade(url)
    yield url
    from agent_fleet.database import engine as engine_mod

    engine_mod.get_engine().dispose()
    _clear_caches()


@pytest.fixture
def session_factory(db_url: str):
    from agent_fleet.database import get_session_factory

    return get_session_factory()


@pytest.fixture
def client(db_url: str):
    from fastapi.testclient import TestClient

    from agent_fleet.main import create_app

    with TestClient(create_app(run_migrations=False)) as c:
        yield c


@pytest.fixture
def workspace_id() -> str:
    from agent_fleet.models import LOCAL_WORKSPACE_ID

    return LOCAL_WORKSPACE_ID


@pytest.fixture
def other_workspace(session_factory) -> str:
    """A second workspace, to prove records never cross workspaces."""
    from agent_fleet.database import session_scope
    from agent_fleet.models import LOCAL_USER_ID, Workspace

    with session_scope(session_factory) as s:
        ws = Workspace(name="Other", owner_id=LOCAL_USER_ID)
        s.add(ws)
        s.flush()
        return ws.id
