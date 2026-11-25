"""FastAPI application (control plane). Binds to 127.0.0.1 by default."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api import routes_entities, routes_runs, routes_system, stream
from .api.errors import install_error_handlers, install_request_logging
from .core.config import get_settings
from .core.logging import configure_logging
from .database.migrate import upgrade

log = logging.getLogger("agent_fleet")


def create_app(*, run_migrations: bool = True) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if run_migrations:
            upgrade()
        log.info("Agent Fleet API ready on %s (local mode)", settings.api_base_url)
        yield

    app = FastAPI(
        title="Agent Fleet",
        version="0.2.0",
        lifespan=lifespan,
        description="Multi-agent orchestration and observability control plane (local mode).",
    )
    # Reject requests whose Host header is not local. This blocks DNS-rebinding pages from using the API.
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=sorted({"127.0.0.1", "localhost", "[::1]", "testserver", settings.api_host}),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "Last-Event-ID", "X-Agent-Fleet-Workspace"],
    )
    install_request_logging(app)
    install_error_handlers(app)
    for module in (routes_system, routes_runs, routes_entities, stream):
        app.include_router(module.router)
    return app


def run() -> None:
    import uvicorn

    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.api_host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("API is bound to %s. Local mode has no authentication; keep it on 127.0.0.1.", settings.api_host)
    uvicorn.run(create_app(), host=settings.api_host, port=settings.api_port, log_level="warning")
