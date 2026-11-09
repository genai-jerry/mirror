"""The app factory.

`create_app()` builds one FastAPI application: structured logging on standard
output, a request id on every request, the one error shape, and the routes.
Later tasks add their routers here; nothing else about this module changes.

`app` at the bottom is what uvicorn is pointed at (`app.main:app`).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .errors import ApiError, api_error_handler, error_body
from .logging_setup import configure_logging, log_event, set_request_id
from .routes import health
from .settings import Settings, load_settings

REQUEST_ID_HEADER = "X-Request-Id"


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    resolved = settings or load_settings()

    app = FastAPI(
        title="Mirror translate proxy",
        version=__version__,
        description="Reads text in a camera frame and answers with its translation.",
    )
    app.state.settings = resolved
    app.add_exception_handler(ApiError, api_error_handler)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            set_request_id(None)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Never leak a traceback or a key to the caller; log it instead."""
        log_event(
            "request.failed",
            level=logging.ERROR,
            message=f"{type(exc).__name__}: {exc}",
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", "The backend could not answer this request."),
        )

    app.include_router(health.router)

    log_event(
        "service.started",
        version=__version__,
        config_dir=str(resolved.config_dir),
        admin_enabled=resolved.admin_enabled,
        app_token_required=resolved.app_token_required,
    )
    return app


app = create_app()
