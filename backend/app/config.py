"""Reading and writing the backend's JSON configuration files.

Two places hold configuration (design decision D6):

* `backend/config/defaults/` — what the service ships with, in git.
* the override directory, `BACKEND_CONFIG_DIR` (default `./runtime-config`) —
  what an operator has changed since.

An override is a *whole* file, so it replaces the shipped file of the same
name rather than merging into it; that is what makes "restore the shipped
configuration" a file deletion.

Reading is cheap because a file is parsed again only when it has changed: each
read stats the file that answers and reuses what was parsed while its
modification time and size are the same ones. That is the whole of the cache —
there is no lifetime and no size to tune, and a change an operator makes takes
effect on the next request with no restart. A write through this module forgets
the file it wrote, so a change made twice inside one clock tick is still seen.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from .settings import Settings

#: The configuration files this service owns. Only these may be written as an
#: override, and `remove_overrides` restores exactly these to what shipped.
MANAGED_CONFIGS = ("budget", "languages")

# One entry per file that has answered. In production that is at most one file
# per name per directory; the limit only stops a long-lived process that reads
# from many directories (a test suite) from remembering all of them for ever.
_CACHE_LIMIT = 64


class ConfigError(Exception):
    """A configuration file is missing, unreadable, or not what it must be."""


@dataclass(frozen=True)
class _CachedFile:
    """What one file held, and how to tell that it still holds it."""

    mtime_ns: int
    size: int
    parsed: dict[str, Any]


_cache: dict[Path, _CachedFile] = {}
_cache_lock = Lock()


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
    # A copy, so a caller that edits what it was given cannot change what the
    # next caller reads.
    return deepcopy(_read(path))


def write_override(name: str, payload: dict[str, Any], settings: Settings) -> Path:
    """Store `payload` as the operator's version of `<name>.json`.

    The file is replaced in one step, so a request reading configuration at the
    same moment sees either the whole old file or the whole new one. Writing the
    same payload twice leaves the same bytes, which is what makes the admin
    endpoints idempotent.
    """
    if name not in MANAGED_CONFIGS:
        raise ValueError(f"{name} is not a configuration file this service owns")
    path = override_path(name, settings)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ConfigError(f"cannot write {path}: {exc}") from exc
    forget(path)
    return path


def remove_overrides(settings: Settings) -> list[str]:
    """Delete every override, restoring the shipped configuration.

    Returns the file names actually removed, so a second call returns an empty
    list rather than failing.
    """
    removed: list[str] = []
    for name in MANAGED_CONFIGS:
        path = override_path(name, settings)
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ConfigError(f"cannot remove {path}: {exc}") from exc
        forget(path)
        removed.append(path.name)
    return removed


def forget(path: Path | None = None) -> None:
    """Forget what one file held, or all of them. The next read parses again."""
    with _cache_lock:
        if path is None:
            _cache.clear()
        else:
            _cache.pop(path, None)


def _read(path: Path) -> dict[str, Any]:
    """What `path` holds, parsed again only if it has changed since last time."""
    stat = _stat(path)
    with _cache_lock:
        remembered = _cache.get(path)
    if (
        remembered is not None
        and remembered.mtime_ns == stat.st_mtime_ns
        and remembered.size == stat.st_size
    ):
        return remembered.parsed

    parsed = _parse(path)
    with _cache_lock:
        if path not in _cache and len(_cache) >= _CACHE_LIMIT:
            _cache.clear()
        _cache[path] = _CachedFile(mtime_ns=stat.st_mtime_ns, size=stat.st_size, parsed=parsed)
    return parsed


def _stat(path: Path) -> os.stat_result:
    try:
        return path.stat()
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc


def _parse(path: Path) -> dict[str, Any]:
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
