"""The admin configuration surface — how a change reaches a running backend.

Three endpoints, all behind `ADMIN_TOKEN` (`app.auth`), all idempotent:

* `PUT /v1/admin/config/languages` — store a whole languages file.
* `PUT /v1/admin/config/budget` — store a whole budget file.
* `DELETE /v1/admin/config/overrides` — remove every override, restoring the
  configuration the service shipped with.

A body is a *whole* file, never a patch, because an override replaces the
shipped file of the same name (design decision D6). A file the service could
not use is refused before it is stored, so an operator is told what is wrong
instead of finding out from the next request.

Both the operator making a change by hand and the system test data loader use
this surface, which is why all three endpoints live together.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..auth import require_admin_token, settings_of
from ..config import ConfigError, remove_overrides, write_override
from ..errors import ApiError
from ..languages import parse_language_config
from ..logging_setup import log_event

router = APIRouter(
    prefix="/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_token)],
)

#: The budget file's shape. Its meaning — how the per-minute window and the
#: wait deadline behave — belongs to the rate budget, not to this surface.
BUDGET_COUNTS = ("recognition_per_minute", "translation_per_minute")
BUDGET_FIELDS = (*BUDGET_COUNTS, "max_wait_seconds")
#: Fields a budget file may leave out. The translation cache's lifetime has a
#: default of its own (`app.translation_cache`), so a file written before the
#: cache existed — and the system test data loader's low-budget set — is still
#: a whole file.
BUDGET_OPTIONAL_SECONDS = ("translation_cache_seconds",)


@router.put("/config/languages")
async def put_languages(request: Request) -> dict[str, str]:
    """Replace the languages configuration. The next request reads the new one."""
    payload = await _json_object(request)
    try:
        parse_language_config(payload)
    except ConfigError as exc:
        raise _refused("languages", exc) from exc
    return _store("languages", payload, request)


@router.put("/config/budget")
async def put_budget(request: Request) -> dict[str, str]:
    """Replace the budget configuration. The next request reads the new one."""
    payload = await _json_object(request)
    try:
        _check_budget(payload)
    except ConfigError as exc:
        raise _refused("budget", exc) from exc
    return _store("budget", payload, request)


@router.delete("/config/overrides")
async def delete_overrides(request: Request) -> dict[str, Any]:
    """Remove every override, restoring the shipped configuration."""
    try:
        removed = remove_overrides(settings_of(request))
    except ConfigError as exc:
        raise ApiError(500, "configuration_not_written", str(exc)) from exc
    log_event("config.overrides_removed", removed=removed)
    return {"status": "restored", "removed": removed}


def _store(name: str, payload: dict[str, Any], request: Request) -> dict[str, str]:
    try:
        write_override(name, payload, settings_of(request))
    except ConfigError as exc:
        raise ApiError(500, "configuration_not_written", str(exc)) from exc
    log_event("config.override_written", name=name)
    return {"status": "stored", "name": name}


async def _json_object(request: Request) -> dict[str, Any]:
    """The request body as a JSON object, or the one error shape explaining why not."""
    body = await request.body()
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ApiError(
            400,
            "invalid_configuration",
            f"The request body is not valid JSON: {exc}.",
        ) from exc
    if not isinstance(parsed, dict):
        raise ApiError(
            400,
            "invalid_configuration",
            "The request body must be a whole configuration file, as a JSON object.",
        )
    return parsed


def _refused(name: str, exc: ConfigError) -> ApiError:
    return ApiError(
        400,
        "invalid_configuration",
        f"This {name} configuration was not stored: {exc}.",
        log_fields={"name": name},
    )


def _check_budget(payload: dict[str, Any]) -> None:
    """Every field the budget file holds, each one a number the budget can use."""
    unknown = sorted(set(payload) - set(BUDGET_FIELDS) - set(BUDGET_OPTIONAL_SECONDS))
    if unknown:
        raise ConfigError(f"{', '.join(unknown)} is not part of the budget configuration")
    missing = [name for name in BUDGET_FIELDS if name not in payload]
    if missing:
        raise ConfigError(
            f"a whole budget file needs {', '.join(missing)} as well — "
            "an override replaces the shipped file rather than adding to it"
        )
    for name in BUDGET_COUNTS:
        value = payload[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(f"{name} must be a whole number of calls, at least 1")
    for name in ("max_wait_seconds", *BUDGET_OPTIONAL_SECONDS):
        if name not in payload:
            continue
        seconds = payload[name]
        if isinstance(seconds, bool) or not isinstance(seconds, int | float) or seconds < 0:
            raise ConfigError(f"{name} must be a number of seconds, 0 or more")
