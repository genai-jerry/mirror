"""The one error shape every endpoint answers with.

`{"error": {"code": "<machine_code>", "message": "<plain sentence>"}}` — the
app reads `code` to decide what to do and shows nothing of `message` to the
person, so the message is for an operator reading a log or a response by hand.
Raise `ApiError` from anywhere; the handler registered by `app.main` turns it
into that shape and logs one `request.rejected` line.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from .logging_setup import log_event


class ApiError(Exception):
    """An answer the caller gets instead of a result."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
        log_fields: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}
        self.log_fields = log_fields or {}


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    log_event(
        "request.rejected",
        code=exc.code,
        status=exc.status_code,
        path=request.url.path,
        **exc.log_fields,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message),
        headers=exc.headers,
    )
