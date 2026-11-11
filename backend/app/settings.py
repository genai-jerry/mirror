"""Deployment facts and secrets, read from the environment only.

Everything that is *configuration* (languages, providers, budgets) lives in
JSON files instead — see `app.config` and design decision D6. The environment
carries only secrets and where-things-are.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULTS_DIR = Path(__file__).resolve().parent.parent / "config" / "defaults"


@dataclass(frozen=True)
class Settings:
    """One snapshot of the environment, taken when the app is created."""

    sarvam_api_key: str | None
    admin_token: str | None
    app_token: str | None
    config_dir: Path
    defaults_dir: Path

    @property
    def admin_enabled(self) -> bool:
        """Admin endpoints exist only when an admin token is set (D6)."""
        return bool(self.admin_token)

    @property
    def app_token_required(self) -> bool:
        """The app token is an opt-in switch, off by default (D10)."""
        return bool(self.app_token)


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def load_settings() -> Settings:
    return Settings(
        sarvam_api_key=_env("SARVAM_API_KEY"),
        admin_token=_env("ADMIN_TOKEN"),
        app_token=_env("APP_TOKEN"),
        config_dir=Path(os.environ.get("BACKEND_CONFIG_DIR") or "./runtime-config"),
        defaults_dir=DEFAULTS_DIR,
    )
