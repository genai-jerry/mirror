"""`GET /v1/languages` — what the app's language picker shows.

The answer is configuration, read on every request (design decision D6), so a
language an operator adds appears in the picker the next time the app asks for
the list — no app release, no restart. Codes and names only: which provider
serves a language is the backend's business.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from ..auth import require_app_token, settings_of
from ..config import ConfigError
from ..errors import ApiError
from ..languages import load_language_config
from ..logging_setup import log_event

router = APIRouter(prefix="/v1", tags=["languages"])


@router.get("/languages", dependencies=[Depends(require_app_token)])
async def languages(request: Request) -> dict[str, list[dict[str, str]]]:
    """The supported source and target languages, straight from configuration."""
    try:
        config = load_language_config(settings_of(request))
    except ConfigError as exc:
        # Only a file edited past the admin endpoint can get here: that endpoint
        # refuses a configuration the service cannot use. The operator needs the
        # detail, the app does not.
        log_event(
            "config.invalid",
            level=logging.ERROR,
            message=str(exc),
            name="languages",
        )
        raise ApiError(
            500,
            "invalid_configuration",
            "The backend's language configuration cannot be read.",
        ) from exc
    return config.picker_payload()
