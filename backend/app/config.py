"""Reading the backend's JSON configuration files.

Two places hold configuration (design decision D6):

* `backend/config/defaults/` — what the service ships with, in git.
* the override directory, `BACKEND_CONFIG_DIR` (default `./runtime-config`) —
  what an operator has changed since.

An override is a *whole* file, so it replaces the shipped file of the same
name rather than merging into it; that is what makes "restore the shipped
configuration" a file deletion. Nothing is cached here yet: re-reading on
change is the languages task's job, and a loader that cached would have to be
unpicked first.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .settings import Settings


class ConfigError(Exception):
    """A configuration file is missing, unreadable, or not a JSON object."""


def override_path(name: str, settings: Settings) -> Path:
    """Where an operator's version of `<name>.json` would be."""
    return settings.config_dir / f"{name}.json"


def default_path(name: str, settings: Settings) -> Path:
    """Where the shipped version of `<name>.json` is."""
    return settings.defaults_dir / f"{name}.json"


def resolve_path(name: str, settings: Settings) -> Path | None:
    """The file that answers for `name` right now, or None if there is none."""
    for candidate in (override_path(name, settings), default_path(name, settings)):
        if candidate.is_file():
            return candidate
    return None


def load_config(name: str, settings: Settings) -> dict[str, Any]:
    """Read `<name>.json`, preferring the operator's override over the default."""
    path = resolve_path(name, settings)
    if path is None:
        raise ConfigError(
            f"no configuration file named {name}.json in "
            f"{settings.config_dir} or {settings.defaults_dir}"
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ConfigError(f"{path} must hold a JSON object, found {type(parsed).__name__}")
    return parsed
