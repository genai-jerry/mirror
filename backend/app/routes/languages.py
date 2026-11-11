"""`GET /v1/languages` — what the app's language picker shows.

The answer is configuration, read on every request (design decision D6), so a
language an operator adds appears in the picker the next time the app asks for
the list — no app release, no restart. Codes and names only: which provider
serves a language is the backend's business.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth import require_app_token, settings_of
from ..languages import load_language_config_or_refuse

router = APIRouter(prefix="/v1", tags=["languages"])


@router.get("/languages", dependencies=[Depends(require_app_token)])
async def languages(request: Request) -> dict[str, list[dict[str, str]]]:
    """The supported source and target languages, straight from configuration."""
    return load_language_config_or_refuse(settings_of(request)).picker_payload()
