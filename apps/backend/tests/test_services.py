import uuid

import pytest
from sqlalchemy import select

from agent_fleet.core.enums import (
    AgentStatus,
    EventSource,
    PermissionPolicy,
    ProviderName,
    RunSource,
    RunStatus,
    TaskStatus,
)
from agent_fleet.core.errors import (
    InvalidTransitionError,
    LimitExceededError,
    NotFoundError,
    RuntimeUnavailableError,
    ValidationFailedError,
)
from agent_fleet.database import session_scope
from agent_fleet.models import Agent, RunEvent, Task
from agent_fleet.services.agents import AgentService
from agent_fleet.services.events import EventService
from agent_fleet.services.messages import MessageService
from agent_fleet.services.runs import NewRun, RunService
from agent_fleet.services.tasks import TaskService

SRC = EventSource.MCP


def new_run(factory, ws, **kw) -> str:
    with session_scope(factory) as s:
        data = NewRun(task_description=kw.pop("task", "Investigate the build"), **kw)
        return RunService(s, ws, SRC).create(data).id


def events(factory, run_id) -> list[RunEvent]:
    with session_scope(factory) as s:
        return list(s.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.sequence_number)))


def test_dashboard_run_is_queued_with_events(session_factory, workspace_id):
    run_id = new_run(session_factory, workspace_id, title="Build check")
    with session_scope(session_factory) as s:
        run = RunService(s, workspace_id, SRC).snapshot(run_id)["run"]
        assert run.status == RunStatus.QUEUED and run.title == "Build check" and run.started_at is None
    assert [e.event_type for e in events(session_factory, run_id)] == ["run.created", "run.queued"]


def test_claude_code_run_starts_running(session_factory, workspace_id):
    run_id = new_run(session_factory, workspace_id, source=RunSource.CLAUDE_CODE, session_id="sess-1")
    evts = events(session_factory, run_id)
    assert [e.event_type for e in evts] == ["run.created", "run.started"]
    with session_scope(session_factory) as s:
        run = RunService(s, workspace_id, SRC).snapshot(run_id)["run"]
        assert run.status == RunStatus.RUNNING and run.session_id == "sess-1" and run.started_at is not None


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"task": "   "}, ValidationFailedError),
        ({"task": "x" * 20_001}, ValidationFailedError),
        ({"orchestrator_model": "gpt-4"}, ValidationFailedError),
        ({"provider": ProviderName.ANTHROPIC_API}, RuntimeUnavailableError),
        ({"permission_policy": PermissionPolicy.WORKSPACE_EDIT}, ValidationFailedError),  # no confirmation
        ({"workspace_path": "relative/path"}, ValidationFailedError),
        ({"max_concurrent_agents": 0}, ValidationFailedError),
    ],
)
def test_run_creation_validation(session_factory, workspace_id, kwargs, error):
    with pytest.raises(error):
        new_run(session_factory, workspace_id, **kwargs)


def test_workspace_path_cannot_escape_allowed_roots(session_factory, workspace_id, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValidationFailedError, match="outside the allowed"):
        new_run(session_factory, workspace_id, workspace_path=str(outside))
    traversal = tmp_path / "workspaces" / ".." / "outside"
    with pytest.raises(ValidationFailedError, match="outside the allowed"):
        new_run(session_factory, workspace_id, workspace_path=str(traversal))
    inside = tmp_path / "workspaces" / "proj"
    inside.mkdir()
    run_id = new_run(
        session_factory,
        workspace_id,
        workspace_path=str(inside),
        permission_policy=PermissionPolicy.WORKSPACE_EDIT,
        confirm_workspace_edit=True,
    )
    types = [e.event_type for e in events(session_factory, run_id)]
    assert "approval.approved" in types


def test_run_state_machine(session_factory, workspace_id):
    run_id = new_run(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        svc = RunService(s, workspace_id, SRC)
        run = svc.snapshot(run_id)["run"]
        with pytest.raises(InvalidTransitionError):
            svc.transition(run, RunStatus.COMPLETED, "skip ahead")  # queued -> completed is not allowed
        svc.transition(run, RunStatus.PLANNING, "claimed")
        svc.transition(run, RunStatus.RUNNING, "session started")
        svc.complete(run_id, "All done")
    with session_scope(session_factory) as s:
        svc = RunService(s, workspace_id, SRC)
        with pytest.raises(InvalidTransitionError):
            svc.fail(run_id, "too late")
        with pytest.raises(InvalidTransitionError):
            svc.cancel(run_id)


def _agents_and_task(factory, ws):
    run_id = new_run(factory, ws, source=RunSource.CLAUDE_CODE)
    with session_scope(factory) as s:
        agents = AgentService(s, ws, SRC)
        root = agents.register(run_id, "orchestrator", "orchestrator", "sonnet")
        worker = agents.register(run_id, "researcher-1", "researcher", "haiku", root.id)
        task = TaskService(s, ws, SRC).create(run_id, "Find sources", "Collect three sources", worker.id)
        return run_id, root.id, worker.id, task.id


def test_agent_registration_and_hierarchy(session_factory, workspace_id):
    run_id, root_id, worker_id, _ = _agents_and_task(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        snap = RunService(s, workspace_id, SRC).snapshot(run_id)
        assert snap["run"].root_agent_id == root_id
        root = s.get(Agent, root_id)
        worker = s.get(Agent, worker_id)
        assert root.status == AgentStatus.RUNNING and worker.status == AgentStatus.QUEUED
        assert worker.parent_agent_id == root_id
        assert snap["hierarchy"][0]["agent_id"] == root_id
        assert snap["hierarchy"][0]["children"][0]["agent_id"] == worker_id


def test_agent_validation_and_transitions(session_factory, workspace_id):
    run_id, root_id, worker_id, _ = _agents_and_task(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        agents = AgentService(s, workspace_id, SRC)
        with pytest.raises(ValidationFailedError):
            agents.register(run_id, "bad;name", "researcher", "haiku")
        with pytest.raises(NotFoundError):
            agents.register(run_id, "x", "researcher", "haiku", str(uuid.uuid4()))
        with pytest.raises(ValidationFailedError):
            agents.update_status(run_id, worker_id, "dancing")
        agents.update_status(run_id, worker_id, AgentStatus.RUNNING)
        agents.update_status(run_id, worker_id, AgentStatus.COMPLETED)
        with pytest.raises(InvalidTransitionError):
            agents.update_status(run_id, worker_id, AgentStatus.RUNNING)
    types = [e.event_type for e in events(session_factory, run_id)]
    assert "agent.started" in types and "agent.completed" in types


def test_concurrency_limit_for_subagents(session_factory, workspace_id):
    run_id = new_run(session_factory, workspace_id, source=RunSource.CLAUDE_CODE, max_concurrent_agents=2)
    with session_scope(session_factory) as s:
        agents = AgentService(s, workspace_id, SRC)
        root = agents.register(run_id, "orchestrator", "orchestrator", "sonnet")
        a = agents.register(run_id, "a", "researcher", "haiku", root.id, status=AgentStatus.RUNNING)
        agents.register(run_id, "b", "analyst", "haiku", root.id, status=AgentStatus.RUNNING)
        c = agents.register(run_id, "c", "reviewer", "sonnet", root.id)  # queued is fine
        with pytest.raises(LimitExceededError):
            agents.update_status(run_id, c.id, AgentStatus.RUNNING)
        agents.update_status(run_id, a.id, AgentStatus.COMPLETED)
        agents.update_status(run_id, c.id, AgentStatus.RUNNING)  # a slot is free again


def test_task_lifecycle_and_result(session_factory, workspace_id):
    run_id, root_id, worker_id, task_id = _agents_and_task(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        tasks = TaskService(s, workspace_id, SRC)
        with pytest.raises(ValidationFailedError):
            tasks.update_status(run_id, task_id, TaskStatus.IN_PROGRESS, 101)
        t = tasks.update_status(run_id, task_id, TaskStatus.IN_PROGRESS)
        assert t.started_at is not None and s.get(Agent, worker_id).current_task_id == task_id
        tasks.update_status(run_id, task_id, None, 40)
        assert t.progress_percentage == 40
        t = tasks.submit_result(run_id, task_id, worker_id, "Three sources found", {"sources": ["a", "b", "c"]})
        assert t.status == TaskStatus.COMPLETED and t.progress_percentage == 100 and t.result_payload["sources"]
        assert s.get(Agent, worker_id).current_task_id is None
        with pytest.raises(InvalidTransitionError):
            tasks.update_status(run_id, task_id, TaskStatus.IN_PROGRESS)
    types = [e.event_type for e in events(session_factory, run_id)]
    assert types.count("task.created") == 1 and "task.started" in types and "task.progress" in types
    assert types[-1] == "task.completed"


def test_only_related_agents_can_submit_results(session_factory, workspace_id):
    run_id, root_id, worker_id, task_id = _agents_and_task(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        stranger = AgentService(s, workspace_id, SRC).register(run_id, "other", "analyst", "haiku", root_id)
        with pytest.raises(ValidationFailedError, match="only the assigned"):
            TaskService(s, workspace_id, SRC).submit_result(run_id, task_id, stranger.id, "not mine")


def test_message_persistence_and_redaction(session_factory, workspace_id):
    run_id, root_id, worker_id, task_id = _agents_and_task(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        msg = MessageService(s, workspace_id, SRC).send(
            run_id,
            root_id,
            "Use key sk-ant-abcdefghijklmnop123 please",
            message_type="instruction",
            receiver_agent_id=worker_id,
            task_id=task_id,
            metadata={"api_key": "secret-value", "input_tokens": 12},
        )
        assert "sk-ant" not in msg.content and "[redacted]" in msg.content
        assert msg.metadata_json == {"api_key": "[redacted]", "input_tokens": 12}
    evt = events(session_factory, run_id)[-1]
    assert evt.event_type == "message.sent" and evt.payload_json["receiver_agent_id"] == worker_id


def test_event_ordering_and_idempotency(session_factory, workspace_id):
    run_id = new_run(session_factory, workspace_id, source=RunSource.CLAUDE_CODE)
    with session_scope(session_factory) as s:
        run = RunService(s, workspace_id, SRC).snapshot(run_id)["run"]
        es = EventService(s)
        first = es.emit(run, "tool.started", "a", source=SRC, idempotency_key="k1")
        again = es.emit(run, "tool.started", "a", source=SRC, idempotency_key="k1")
        es.emit(run, "tool.completed", "b", source=SRC, payload={"thinking": "hidden", "ok": True})
        assert first.id == again.id
    seqs = [e.sequence_number for e in events(session_factory, run_id)]
    assert seqs == list(range(1, len(seqs) + 1))
    assert events(session_factory, run_id)[-1].payload_json == {"ok": True}  # reasoning keys are dropped


def test_append_event_rejects_state_events(session_factory, workspace_id):
    run_id, root_id, _, _ = _agents_and_task(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        msgs = MessageService(s, workspace_id, SRC)
        with pytest.raises(ValidationFailedError):
            msgs.append_event(run_id, "run.completed", "cheating")
        with pytest.raises(ValidationFailedError):
            msgs.append_event(run_id, "made.up", "x")
        e = msgs.append_event(run_id, "tool.started", "grep", agent_id=root_id, payload={"tool_name": "Grep"})
        assert e.agent_id == root_id


def test_invalid_and_missing_ids(session_factory, workspace_id):
    with session_scope(session_factory) as s:
        svc = RunService(s, workspace_id, SRC)
        with pytest.raises(ValidationFailedError):
            svc.snapshot("not-a-uuid")
        with pytest.raises(NotFoundError):
            svc.snapshot(str(uuid.uuid4()))


def test_workspace_isolation(session_factory, workspace_id, other_workspace):
    run_id, root_id, worker_id, task_id = _agents_and_task(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        with pytest.raises(NotFoundError):
            RunService(s, other_workspace, SRC).snapshot(run_id)
        with pytest.raises(NotFoundError):
            AgentService(s, other_workspace, SRC).update_status(run_id, worker_id, AgentStatus.RUNNING)
        with pytest.raises(NotFoundError):
            TaskService(s, other_workspace, SRC).submit_result(run_id, task_id, worker_id, "x")
    # And an agent from another run of the same workspace cannot be used in this run.
    other_run = new_run(session_factory, workspace_id, source=RunSource.CLAUDE_CODE)
    with session_scope(session_factory) as s:
        with pytest.raises(NotFoundError):
            TaskService(s, workspace_id, SRC).create(other_run, "t", "d", worker_id)


def test_cancel_closes_open_work(session_factory, workspace_id):
    run_id, root_id, worker_id, task_id = _agents_and_task(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        RunService(s, workspace_id, SRC).cancel(run_id)
    with session_scope(session_factory) as s:
        assert s.get(Agent, worker_id).status == AgentStatus.CANCELLED
        assert s.get(Task, task_id).status == TaskStatus.CANCELLED
        with pytest.raises(InvalidTransitionError):
            AgentService(s, workspace_id, SRC).register(run_id, "late", "analyst", "haiku")
    implicit = [e for e in events(session_factory, run_id) if (e.payload_json or {}).get("implicit")]
    assert implicit, "system-closed records must be flagged as implicit"


def test_fail_run_records_error(session_factory, workspace_id):
    run_id, *_ = _agents_and_task(session_factory, workspace_id)
    with session_scope(session_factory) as s:
        run = RunService(s, workspace_id, SRC).fail(run_id, "Rate limit reached")
        assert run.status == RunStatus.FAILED and run.error_message == "Rate limit reached"
    assert events(session_factory, run_id)[-1].event_type in ("task.status_changed", "agent.status_changed")
    assert "run.failed" in [e.event_type for e in events(session_factory, run_id)]
