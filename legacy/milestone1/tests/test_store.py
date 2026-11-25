import sqlite3
import uuid

import pytest

from agent_fleet.models import EventType, RunStatus
from agent_fleet.store import DB_PATH_ENV, RunNotFoundError, RunStateError, RunStore, default_db_path


@pytest.fixture
def store(tmp_path):
    return RunStore(tmp_path / "test.db")


def test_full_lifecycle(store):
    run = store.create_run("Refactor auth module", "claude_code")
    assert uuid.UUID(run.run_id)
    assert run.status == RunStatus.CREATED
    assert run.created_at.utcoffset().total_seconds() == 0

    store.append_event(run.run_id, "run.started", "Starting")
    assert store.get_run(run.run_id).status == RunStatus.RUNNING

    store.append_event(run.run_id, "agent.started", "Planner up", agent_id="planner")
    store.append_event(
        run.run_id, "task.created", "Write tests", agent_id="worker-1",
        parent_agent_id="planner", task_id="t1", payload={"files": ["a.py"], "n": 2},
    )
    done = store.finish_run(run.run_id, "completed", "All good")
    assert done.status == RunStatus.COMPLETED and done.summary == "All good"
    assert done.updated_at >= run.updated_at

    events = store.list_events(run.run_id)
    assert [e.event_type for e in events] == [
        EventType.RUN_CREATED, EventType.RUN_STARTED, EventType.AGENT_STARTED,
        EventType.TASK_CREATED, EventType.RUN_COMPLETED,
    ]
    task_ev = events[3]
    assert (task_ev.agent_id, task_ev.parent_agent_id, task_ev.task_id) == ("worker-1", "planner", "t1")
    assert task_ev.payload == {"files": ["a.py"], "n": 2}
    assert events[1].payload is None


def test_failed_run_records_run_failed(store):
    run = store.create_run("x", "api")
    store.finish_run(run.run_id, "failed", "boom")
    assert store.list_events(run.run_id)[-1].event_type == EventType.RUN_FAILED


@pytest.mark.parametrize("task,source", [("", "api"), ("   ", "api"), ("x" * 10_001, "api"), ("ok", "slack")])
def test_create_run_validation(store, task, source):
    with pytest.raises(ValueError):
        store.create_run(task, source)


def test_unknown_and_malformed_run_ids(store):
    with pytest.raises(ValueError, match="UUID"):
        store.get_run("not-a-uuid")
    with pytest.raises(RunNotFoundError):
        store.get_run(str(uuid.uuid4()))
    with pytest.raises(RunNotFoundError):
        store.append_event(str(uuid.uuid4()), "message.sent", "hi")
    with pytest.raises(RunNotFoundError):
        store.list_events(str(uuid.uuid4()))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"event_type": "agent.exploded", "message": "x"},
        {"event_type": "run.completed", "message": "x"},  # lifecycle: finish_run only
        {"event_type": "run.created", "message": "x"},
        {"event_type": "message.sent", "message": ""},
        {"event_type": "message.sent", "message": "x", "payload": {"bad": object()}},
        {"event_type": "message.sent", "message": "x", "payload": ["not", "an", "object"]},
        {"event_type": "message.sent", "message": "x", "payload": {"big": "x" * 100_001}},
    ],
)
def test_append_event_validation(store, kwargs):
    run = store.create_run("x", "dashboard")
    with pytest.raises(ValueError):
        store.append_event(run.run_id, **kwargs)
    assert len(store.list_events(run.run_id)) == 1  # nothing partial written


def test_finished_run_is_closed(store):
    run = store.create_run("x", "api")
    store.finish_run(run.run_id, "completed")
    with pytest.raises(RunStateError):
        store.append_event(run.run_id, "message.sent", "late")
    with pytest.raises(RunStateError):
        store.finish_run(run.run_id, "failed")


@pytest.mark.parametrize("status", ["running", "created", "done"])
def test_finish_run_rejects_non_terminal_status(store, status):
    run = store.create_run("x", "api")
    with pytest.raises(ValueError):
        store.finish_run(run.run_id, status)


def test_persists_across_instances(tmp_path):
    path = tmp_path / "nested" / "dir" / "fleet.db"
    run_id = RunStore(path).create_run("x", "api").run_id
    assert RunStore(path).get_run(run_id).task == "x"


def test_db_constraints_enforced(store):
    conn = sqlite3.connect(store.db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO run_events VALUES ('e', 'missing', 'message.sent', NULL, NULL, NULL, 'm', NULL, 't')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO runs VALUES ('r', 't', 'nope', 'created', 'a', 'b', NULL)")
    conn.close()


def test_db_path_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "env.db"))
    assert default_db_path() == tmp_path / "env.db"
    assert RunStore().db_path == tmp_path / "env.db"
