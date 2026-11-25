"""Consistent error responses: {"error": {"code", "message", "details"}}."""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..core.errors import AgentFleetError

log = logging.getLogger("agent_fleet.api")


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message, "details": details or {}}}
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AgentFleetError)
    async def _domain(_: Request, exc: AgentFleetError) -> JSONResponse:
        return _error(exc.http_status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()
        ]
        return _error(422, "validation_failed", "request validation failed", {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return _error(500, "internal_error", "internal server error")


def install_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def _log(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        # Path only: query strings and bodies are never logged, so secrets in them cannot leak.
        log.info(
            "%s %s -> %s (%.0f ms)",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - start) * 1000,
        )
        return response
