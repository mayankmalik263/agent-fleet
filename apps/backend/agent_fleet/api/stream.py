"""Server-Sent Events for one run.

Persisted events are the source of truth: the stream polls run_events, so events written by any
process (API, runner, MCP server) reach the browser. Each message carries `id: <sequence_number>`;
a reconnecting EventSource sends Last-Event-ID and the stream resumes after it (no gaps, no duplicates).
"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.state_machine import RUN_TERMINAL
from ..core.time import utcnow
from ..database import session_scope
from ..models import Run, RunEvent
from ..repositories import scoped
from ..schemas import EventRead
from ..services.events import events_after
from .deps import DB, WorkspaceId

router = APIRouter(prefix="/api/v1", tags=["events"])

POLL_SECONDS = 0.5
END_GRACE_SECONDS = 90
HEARTBEAT_SECONDS = 15.0


def _fetch(workspace_id: str, run_id: str, cursor: int) -> tuple[list[str], int, bool]:
    with session_scope(readonly=True) as session:
        run = scoped.get_run(session, workspace_id, run_id)
        events = events_after(session, workspace_id, run_id, cursor, limit=500)
        frames = [f"id: {e.sequence_number}\ndata: {EventRead.model_validate(e).model_dump_json()}\n\n" for e in events]
        new_cursor = events[-1].sequence_number if events else cursor
        return frames, new_cursor, _stream_finished(session, run, new_cursor)


def _stream_finished(session: Session, run: Run, cursor: int) -> bool:
    """End the stream only when no more events can come. A runner-managed run writes its last events
    (usage, session end, runner.disconnected) after the run status became final, so wait for them."""
    if run.status not in RUN_TERMINAL or cursor < run.event_seq:
        return False
    if run.runner_device_id is None:
        return True
    disconnected = session.scalar(
        select(RunEvent.id).where(RunEvent.run_id == run.id, RunEvent.event_type == "runner.disconnected").limit(1)
    )
    grace_over = run.completed_at is not None and utcnow() - run.completed_at > timedelta(seconds=END_GRACE_SECONDS)
    return disconnected is not None or grace_over


@router.get("/runs/{run_id}/events/stream")
async def stream_events(
    run_id: str,
    request: Request,
    db: DB,
    workspace_id: WorkspaceId,
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    run = scoped.get_run(db, workspace_id, run_id)  # 404 before the stream opens
    run_id = run.id
    db.close()
    cursor = after
    if last_event_id and last_event_id.isdigit():
        cursor = max(cursor, int(last_event_id))

    async def frames() -> AsyncIterator[str]:
        nonlocal cursor
        yield "retry: 2000\n\n"
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            batch, cursor, finished = await run_in_threadpool(_fetch, workspace_id, run_id, cursor)
            for frame in batch:
                yield frame
            if finished:
                yield f"event: end\ndata: {json.dumps({'run_id': run_id, 'last_sequence': cursor})}\n\n"
                return
            if batch:
                idle = 0.0
                continue
            await asyncio.sleep(POLL_SECONDS)
            idle += POLL_SECONDS
            if idle >= HEARTBEAT_SECONDS:
                idle = 0.0
                yield ": keep-alive\n\n"

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
