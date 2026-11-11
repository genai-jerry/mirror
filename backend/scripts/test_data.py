#!/usr/bin/env python3
"""Put this epic's system test data sets into a running backend, and take them out.

The system test plan (`openspec/changes/<epic>/system-tests/test-plan.md`) names
four data sets. Two of them are backend configuration — DS-2's language
configurations and DS-3's low recognition budget — and this is how they reach a
running backend. The other two, DS-1's Malayalam headlines and DS-4's endpoint
request sample, are tester-side materials used straight from the checkout:
nothing loads them anywhere, and asking this script to load one says so.

    uv run --project backend python backend/scripts/test_data.py load <data-dir>
    uv run --project backend python backend/scripts/test_data.py load --set NAME <data-dir>
    uv run --project backend python backend/scripts/test_data.py unload <data-dir>

The data directory is the last argument of both commands, which is the contract
`test_data` in `.factory/profile.json` carries. `unload` needs nothing out of it
— the backend restores the shipped configuration by deleting every override —
but it is named there so both commands take the same shape.

`load` with no `--set` puts the environment in the state every case starts from:
every override removed, then the `baseline` language configuration applied.
`load --set NAME` applies one named set, replacing the one configuration file
that set governs and leaving the other alone — which is what a tester runs for
the case in front of them. Both are safe to repeat: an override is a whole file
that replaces the file of the same name, so a second load writes the same bytes
rather than stacking a second copy of anything.

The backend is reached over HTTP, so "where it runs" is just a URL:

* `BACKEND_URL` — default `http://127.0.0.1:8000`.
* `ADMIN_TOKEN` — the token the backend was started with. The admin endpoints
  do not exist without one, so neither does this script's work.

The provider entries and the display names come from the configuration the
service ships (`backend/config/defaults/`), so a set carries only the facts that
make it that set, and a change to a shipped provider's model reaches the test
configuration with it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.settings import DEFAULTS_DIR

#: Where the backend is, when the environment does not say.
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"

#: Which configuration file each data set governs. A set named in no entry here
#: is tester-side material, and this script refuses to pretend otherwise.
CONFIG_OF_SET = {"DS-2": "languages", "DS-3": "budget"}

#: What `load` applies when no set is named: the state every case starts from.
STARTING_SET = "baseline"

#: The admin surface (design decision D6, `app.routes.admin`).
ADMIN_PATHS = {
    "languages": "/v1/admin/config/languages",
    "budget": "/v1/admin/config/budget",
}
OVERRIDES_PATH = "/v1/admin/config/overrides"

#: The short provider names DS-2 uses, mapped onto the provider entries the
#: shipped configuration names. `sarvam-alt` is the alternate entry ST-8
#: watches for in the backend's log.
PROVIDER_ENTRIES = {
    ("recognition", "sarvam"): "sarvam-parse",
    ("translation", "sarvam"): "sarvam-translate",
    ("translation", "sarvam-alt"): "sarvam-translate-alt",
}

#: Display names for language codes the shipped configuration does not name. A
#: code neither it nor this table knows is shown as itself, which a tester can
#: see is unnamed rather than wrong.
EXTRA_LANGUAGE_NAMES = {"ta-IN": "Tamil"}

#: DS-3's record fields, mapped onto the budget file's fields.
BUDGET_FIELDS = {
    "recognition_requests_per_minute": "recognition_per_minute",
    "translation_requests_per_minute": "translation_per_minute",
    "max_wait_seconds": "max_wait_seconds",
    "translation_cache_seconds": "translation_cache_seconds",
}

#: DS-2's record fields. Everything a record may hold is either one of these,
#: one of the fields a configuration file takes, or prose for a person.
LANGUAGE_FIELDS = ("source_languages", "target_languages", "providers")

#: What a record carries for the person reading it, not for this script.
PROSE_FIELDS = ("id", "name", "note", "how_to_use", "expected")


class LoaderError(Exception):
    """Something a person has to fix: bad data, no backend, a refused change."""


@dataclass(frozen=True)
class DataSet:
    """One record of one set, and the set file it came from."""

    set_id: str
    record: Mapping[str, Any]

    @property
    def name(self) -> str:
        """The record's id — the name `--set` takes."""
        return str(self.record["id"])

    @property
    def config_name(self) -> str | None:
        """The configuration file this set replaces, or None if it loads nowhere."""
        return CONFIG_OF_SET.get(self.set_id)


# --- reading the data directory --------------------------------------------


def read_sets(data_dir: Path) -> dict[str, DataSet]:
    """Every record under `data_dir`, by the name `--set` takes."""
    require_data_dir(data_dir)
    found: dict[str, DataSet] = {}
    for path in sorted(data_dir.glob("DS-*.json")):
        parsed = _read_json(path)
        set_id = _set_id(parsed, path)
        for record in _records(parsed, path):
            name = record["id"]
            if name in found:
                raise LoaderError(
                    f"{found[name].set_id} and {set_id} both hold a record called {name}, "
                    "so --set could not tell them apart"
                )
            found[name] = DataSet(set_id=set_id, record=record)
    if not found:
        raise LoaderError(f"{data_dir} holds no DS-*.json data set records")
    return found


def require_data_dir(data_dir: Path) -> None:
    """Refuse a data directory that is not there, naming the path that was tried."""
    if not data_dir.is_dir():
        raise LoaderError(f"there is no data directory at {data_dir}")


def _set_id(parsed: Mapping[str, Any], path: Path) -> str:
    value = parsed.get("set")
    if not isinstance(value, str) or not value.strip():
        raise LoaderError(f"{path} does not say which set it holds")
    return value.strip()


def _records(parsed: Mapping[str, Any], path: Path) -> list[Mapping[str, Any]]:
    raw = parsed.get("records")
    if not isinstance(raw, list):
        raise LoaderError(f"{path} must hold its records in a JSON list")
    for record in raw:
        if not isinstance(record, Mapping) or not isinstance(record.get("id"), str):
            raise LoaderError(f"every record in {path} must be a JSON object with an id")
    return raw


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LoaderError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LoaderError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LoaderError(f"{path} must hold a JSON object")
    return parsed


# --- turning a record into a whole configuration file ----------------------


def languages_payload(record: Mapping[str, Any], shipped: Mapping[str, Any]) -> dict[str, Any]:
    """DS-2's record as a whole languages file.

    The record carries the languages and which provider serves each one; the
    provider entries themselves, and the display names, come from the shipped
    configuration (`shipped`).
    """
    _reject_unknown_fields(record, LANGUAGE_FIELDS, "a language configuration set")
    names = _shipped_names(shipped)
    serves = _provider_mapping(record)
    sources = []
    for code in _codes(record, "source_languages"):
        entry = serves.get(code)
        if not isinstance(entry, Mapping):
            raise LoaderError(f"source language {code} names no providers in this set")
        sources.append(
            {
                "code": code,
                "name": _language_name(code, names),
                "recognition_provider": _provider_entry("recognition", entry, code),
                "translation_provider": _provider_entry("translation", entry, code),
            }
        )
    targets = [
        {"code": code, "name": _language_name(code, names)}
        for code in _codes(record, "target_languages")
    ]
    return {
        "sources": sources,
        "targets": targets,
        "providers": deepcopy(_shipped_providers(shipped)),
    }


def budget_payload(record: Mapping[str, Any], shipped: Mapping[str, Any]) -> dict[str, Any]:
    """DS-3's record as a whole budget file.

    An override replaces the shipped file rather than adding to it, so the
    fields the set does not speak about — the wait deadline, the cache's
    lifetime — are carried over from what the service ships.
    """
    _reject_unknown_fields(record, tuple(BUDGET_FIELDS), "a budget set")
    payload = dict(shipped)
    for record_field, config_field in BUDGET_FIELDS.items():
        if record_field in record:
            payload[config_field] = record[record_field]
    return payload


#: Which function turns a record into which configuration file.
PAYLOAD_OF: dict[str, Callable[[Mapping[str, Any], Mapping[str, Any]], dict[str, Any]]] = {
    "languages": languages_payload,
    "budget": budget_payload,
}


def shipped_config(name: str, defaults_dir: Path = DEFAULTS_DIR) -> Mapping[str, Any]:
    """The configuration file the service ships as `<name>.json`."""
    return _read_json(defaults_dir / f"{name}.json")


def _reject_unknown_fields(record: Mapping[str, Any], fields: Sequence[str], where: str) -> None:
    unknown = sorted(set(record) - set(fields) - set(PROSE_FIELDS))
    if unknown:
        raise LoaderError(
            f"{', '.join(unknown)} is not something this loader knows how to apply from "
            f"{where} — the data set and this loader have to change together"
        )


def _codes(record: Mapping[str, Any], field: str) -> list[str]:
    raw = record.get(field, [])
    if not isinstance(raw, list) or not all(isinstance(code, str) and code.strip() for code in raw):
        raise LoaderError(f"{field} must be a JSON list of language codes")
    return [code.strip() for code in raw]


def _provider_mapping(record: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = record.get("providers", {})
    if not isinstance(raw, Mapping):
        raise LoaderError("providers must map each source language to the providers that serve it")
    return raw


def _provider_entry(role: str, entry: Mapping[str, Any], code: str) -> str:
    short = entry.get(role)
    if not isinstance(short, str) or not short.strip():
        raise LoaderError(f"source language {code} names no {role} provider")
    name = PROVIDER_ENTRIES.get((role, short.strip()))
    if name is None:
        raise LoaderError(
            f"{short} is not a {role} provider this loader knows — "
            f"it knows {', '.join(sorted(s for r, s in PROVIDER_ENTRIES if r == role))}"
        )
    return name


def _shipped_providers(shipped: Mapping[str, Any]) -> Mapping[str, Any]:
    providers = shipped.get("providers")
    if not isinstance(providers, Mapping) or not providers:
        raise LoaderError("the shipped languages configuration names no provider entries")
    return providers


def _shipped_names(shipped: Mapping[str, Any]) -> dict[str, str]:
    """What the shipped configuration calls each language code it names."""
    names: dict[str, str] = {}
    for field in ("sources", "targets"):
        entries = shipped.get(field)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, Mapping):
                code, name = entry.get("code"), entry.get("name")
                if isinstance(code, str) and isinstance(name, str):
                    names[code.casefold()] = name
    return names


def _language_name(code: str, shipped_names: Mapping[str, str]) -> str:
    return shipped_names.get(code.casefold()) or EXTRA_LANGUAGE_NAMES.get(code, code)


# --- talking to the backend ------------------------------------------------


def load(client: httpx.Client, data_dir: Path, set_name: str | None = None) -> list[str]:
    """Apply one named set, or — with no set named — the state every case starts from."""
    sets = read_sets(data_dir)
    said: list[str] = []
    if set_name is None:
        said.append(remove_overrides(client))
        set_name = STARTING_SET
    chosen, name = _chosen(sets, set_name)
    payload = PAYLOAD_OF[name](chosen.record, shipped_config(name))
    _put(client, ADMIN_PATHS[name], payload)
    said.append(f"{chosen.name} is now the {name} configuration")
    return said


def unload(client: httpx.Client, data_dir: Path) -> list[str]:
    """Remove every override, so the backend answers from what it shipped with."""
    require_data_dir(data_dir)
    return [remove_overrides(client)]


def remove_overrides(client: httpx.Client) -> str:
    """Delete every override. Says what was there, so a second call reads as a no-op."""
    response = _sent(client, "DELETE", OVERRIDES_PATH)
    removed = _removed_names(response)
    if not removed:
        return "no override was in place; the shipped configuration is in force"
    return f"removed the {', '.join(removed)} override; the shipped configuration is back"


def _put(client: httpx.Client, path: str, payload: Mapping[str, Any]) -> None:
    _sent(client, "PUT", path, json=payload)


def _sent(client: httpx.Client, method: str, path: str, **kwargs: Any) -> httpx.Response:
    try:
        response = client.request(method, path, **kwargs)
    except httpx.RequestError as exc:
        raise LoaderError(
            f"cannot reach the backend at {client.base_url}: {exc}. "
            "Set BACKEND_URL to where it runs, and check that it is up."
        ) from exc
    _refuse_unless_stored(response)
    return response


def _refuse_unless_stored(response: httpx.Response) -> None:
    if response.is_success:
        return
    detail = _refusal(response)
    if response.status_code == 404:
        raise LoaderError(
            "this backend has no admin configuration endpoints, so it was started without "
            f"ADMIN_TOKEN set. Restart it with one and try again ({detail})"
        )
    if response.status_code == 401:
        raise LoaderError(f"the backend refused the token in ADMIN_TOKEN ({detail})")
    raise LoaderError(f"the backend refused the change with {response.status_code}: {detail}")


def _refusal(response: httpx.Response) -> str:
    """The backend's own plain sentence about a refusal, whatever shape it came in."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:200] or "no explanation given"
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        error = body["error"]
        return f"{error.get('code')}: {error.get('message')}"
    return json.dumps(body)[:200]


def _removed_names(response: httpx.Response) -> list[str]:
    try:
        body = response.json()
    except ValueError:
        return []
    removed = body.get("removed") if isinstance(body, dict) else None
    if not isinstance(removed, list):
        return []
    return [str(name) for name in removed]


def _chosen(sets: Mapping[str, DataSet], set_name: str) -> tuple[DataSet, str]:
    """The set `--set` names, and the configuration file it replaces."""
    chosen = sets.get(set_name)
    if chosen is None:
        raise LoaderError(
            f"there is no data set called {set_name} here — "
            f"this directory offers {', '.join(_loadable(sets))}"
        )
    if chosen.config_name is None:
        raise LoaderError(
            f"{set_name} belongs to {chosen.set_id}, which is material a tester uses "
            "straight from the checkout: there is nothing to load into a backend"
        )
    return chosen, chosen.config_name


def _loadable(sets: Mapping[str, DataSet]) -> list[str]:
    return sorted(name for name, found in sets.items() if found.config_name is not None)


# --- the command line ------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="test_data.py",
        description=(
            "Put this epic's system test configuration sets into a running backend, "
            "and take them out again."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    loading = commands.add_parser(
        "load",
        help="apply one set, or the state every case starts from",
    )
    loading.add_argument(
        "--set",
        dest="set_name",
        metavar="NAME",
        default=None,
        help=(
            "the set to apply. Without this, every override is removed and the "
            f"{STARTING_SET} set is applied."
        ),
    )
    loading.add_argument(
        "data_dir", metavar="DATA-DIR", type=Path, help="the epic's data directory"
    )

    unloading = commands.add_parser(
        "unload", help="remove every override, restoring the shipped configuration"
    )
    unloading.add_argument(
        "data_dir", metavar="DATA-DIR", type=Path, help="the epic's data directory"
    )
    return parser


def main(argv: Sequence[str] | None = None, client: httpx.Client | None = None) -> int:
    """Run one command. `client` is for the tests: the command line opens its own."""
    args = build_parser().parse_args(argv)
    try:
        if client is not None:
            said = _run(args, client)
        else:
            with _open_client() as opened:
                said = _run(args, opened)
    except LoaderError as exc:
        print(f"test data: {exc}", file=sys.stderr)
        return 1
    for line in said:
        print(f"test data: {line}")
    return 0


def _run(args: argparse.Namespace, client: httpx.Client) -> list[str]:
    if args.command == "load":
        return load(client, args.data_dir, args.set_name)
    return unload(client, args.data_dir)


def _open_client() -> httpx.Client:
    """A client for the backend the environment names, carrying the admin token."""
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        raise LoaderError(
            "set ADMIN_TOKEN to the admin token the backend was started with — "
            "its configuration endpoints do not exist without one"
        )
    base_url = os.environ.get("BACKEND_URL", "").strip() or DEFAULT_BACKEND_URL
    return httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


if __name__ == "__main__":  # pragma: no cover - the command line's own entry
    raise SystemExit(main())
