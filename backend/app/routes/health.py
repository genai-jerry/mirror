"""`GET /healthz` — the liveness answer the factory's health checks read.

No authentication, by design: a health check that needs a token tells you
about the token as much as about the service.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
