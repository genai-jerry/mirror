"""Who may call what.

Two tokens, both sent as `Authorization: Bearer <token>`:

* `ADMIN_TOKEN` decides whether the admin configuration endpoints exist at
  all. Unset, they answer 404 as if there were no such path; set, a call
  without the token is refused with 401.
* `APP_TOKEN` is the optional switch of design decision D10. Unset — the
  default — the app-facing endpoints are open. Set, every one of them needs
  that token. A token shipped inside an installed app is a deterrent, not a
  secret, which is why it is a switch an operator may leave off.

Neither token is read here from the environment: both arrive in `Settings`
(`app.settings`), and neither is ever logged or returned.
"""

from __future__ import annotations

from hmac import compare_digest

from fastapi import Request

from .errors import ApiError
from .settings import Settings

BEARER = "bearer"


def settings_of(request: Request) -> Settings:
    """The settings this app was built with — see `app.main.create_app`."""
    settings: Settings = request.app.state.settings
    return settings


def require_app_token(request: Request) -> None:
    """Refuse an app-facing call when an app token is required and not given."""
    settings = settings_of(request)
    if not settings.app_token_required:
        return
    if not _matches(_bearer_token(request), settings.app_token):
        raise ApiError(
            401,
            "unauthorized",
            "This endpoint needs the app token.",
            log_fields={"reason": "app_token"},
        )


def require_admin_token(request: Request) -> None:
    """Refuse an admin call unless admin is switched on and the token matches."""
    settings = settings_of(request)
    if not settings.admin_enabled:
        raise ApiError(
            404,
            "not_found",
            "There is no such endpoint.",
            log_fields={"reason": "admin_disabled"},
        )
    if not _matches(_bearer_token(request), settings.admin_token):
        raise ApiError(
            401,
            "unauthorized",
            "This endpoint needs the admin token.",
            log_fields={"reason": "admin_token"},
        )


def _bearer_token(request: Request) -> str | None:
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    if scheme.strip().casefold() != BEARER:
        return None
    return value.strip() or None


def _matches(given: str | None, expected: str | None) -> bool:
    """Compare in constant time, so a wrong token tells the caller nothing."""
    if not given or not expected:
        return False
    return compare_digest(given, expected)
