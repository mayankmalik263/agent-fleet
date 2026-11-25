from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from ..database import get_session_factory
from ..models import LOCAL_WORKSPACE_ID
from ..repositories import scoped


def _session(readonly: bool) -> Iterator[Session]:
    session = get_session_factory(readonly=readonly)()
    try:
        yield session
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """Read-only session (deferred transaction; never blocks writers)."""
    yield from _session(readonly=True)


def get_write_db() -> Iterator[Session]:
    """Write session. Routes call db.commit() before they return, so the client never sees data that
    is not durable. Anything not committed is rolled back when the session closes."""
    yield from _session(readonly=False)


def get_workspace_id(x_agent_fleet_workspace: Annotated[str | None, Header()] = None) -> str:
    """Local mode: every request acts in the local workspace unless a header names another one.
    Production needs real authentication and authorization here (see docs/SECURITY.md)."""
    workspace_id = x_agent_fleet_workspace or LOCAL_WORKSPACE_ID
    session = get_session_factory(readonly=True)()
    try:
        return scoped.get_workspace(session, workspace_id).id
    finally:
        session.close()


DB = Annotated[Session, Depends(get_db)]
WriteDB = Annotated[Session, Depends(get_write_db)]
WorkspaceId = Annotated[str, Depends(get_workspace_id)]
