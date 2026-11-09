from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.config import (
    ConfigError,
    load_config,
    remove_overrides,
    resolve_path,
    write_override,
)
from app.settings import Settings, load_settings


def _write_keeping_the_timestamp(path: Path, text: str) -> None:
    """Change a file's contents without changing its modification time.

    Two writes inside one clock tick really do land on the same timestamp; this
    makes that case happen on demand instead of by luck.
    """
    before = path.stat()
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


def test_reads_the_shipped_default(settings: Settings) -> None:
    budget = load_config("budget", settings)

    assert budget["recognition_per_minute"] == 60
    assert budget["max_wait_seconds"] == 15


def test_an_override_replaces_the_shipped_file(settings: Settings) -> None:
    settings.config_dir.mkdir(parents=True)
    (settings.config_dir / "budget.json").write_text(
        json.dumps({"recognition_per_minute": 2}), encoding="utf-8"
    )

    budget = load_config("budget", settings)

    assert budget == {"recognition_per_minute": 2}, "an override is a whole file, not a merge"


def test_removing_the_override_restores_the_default(settings: Settings) -> None:
    settings.config_dir.mkdir(parents=True)
    override = settings.config_dir / "budget.json"
    override.write_text(json.dumps({"recognition_per_minute": 2}), encoding="utf-8")
    assert load_config("budget", settings)["recognition_per_minute"] == 2

    override.unlink()

    assert load_config("budget", settings)["recognition_per_minute"] == 60


def test_a_missing_override_directory_is_not_an_error(settings: Settings) -> None:
    assert not settings.config_dir.exists()

    assert resolve_path("budget", settings) == settings.defaults_dir / "budget.json"


def test_an_unknown_name_says_where_it_looked(settings: Settings) -> None:
    """Both the shipped files exist, so this asks for one that is not a file at all."""
    with pytest.raises(ConfigError) as raised:
        load_config("no-such-configuration", settings)

    assert "no-such-configuration.json" in str(raised.value)
    assert str(settings.config_dir) in str(raised.value)


def test_malformed_json_names_the_file(settings: Settings) -> None:
    settings.config_dir.mkdir(parents=True)
    (settings.config_dir / "budget.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ConfigError) as raised:
        load_config("budget", settings)

    assert "budget.json" in str(raised.value)


def test_a_json_list_is_rejected(settings: Settings) -> None:
    settings.config_dir.mkdir(parents=True)
    (settings.config_dir / "budget.json").write_text("[1, 2]", encoding="utf-8")

    with pytest.raises(ConfigError) as raised:
        load_config("budget", settings)

    assert "JSON object" in str(raised.value)


def test_override_directory_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BACKEND_CONFIG_DIR", str(tmp_path / "elsewhere"))

    assert load_settings().config_dir == tmp_path / "elsewhere"


def test_override_directory_falls_back_to_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BACKEND_CONFIG_DIR", raising=False)

    assert load_settings().config_dir == Path("./runtime-config")


def test_secrets_come_from_the_environment_and_are_absent_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("SARVAM_API_KEY", "ADMIN_TOKEN", "APP_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    loaded = load_settings()

    assert loaded.sarvam_api_key is None
    assert loaded.admin_enabled is False
    assert loaded.app_token_required is False


def test_blank_environment_values_count_as_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "   ")

    assert load_settings().admin_enabled is False


# --- reading again only when the file has changed ---------------------------


def test_an_unchanged_file_is_not_read_again(settings: Settings) -> None:
    """What makes re-reading configuration on every request cheap."""
    settings.config_dir.mkdir(parents=True)
    override = settings.config_dir / "budget.json"
    override.write_text(json.dumps({"recognition_per_minute": 2}), encoding="utf-8")
    assert load_config("budget", settings)["recognition_per_minute"] == 2

    _write_keeping_the_timestamp(override, json.dumps({"recognition_per_minute": 9}))

    assert load_config("budget", settings)["recognition_per_minute"] == 2


def test_a_changed_file_is_read_again(settings: Settings) -> None:
    """An operator's change takes effect on the next request, with no restart."""
    settings.config_dir.mkdir(parents=True)
    override = settings.config_dir / "budget.json"
    override.write_text(json.dumps({"recognition_per_minute": 2}), encoding="utf-8")
    assert load_config("budget", settings)["recognition_per_minute"] == 2

    override.write_text(json.dumps({"recognition_per_minute": 9}), encoding="utf-8")
    os.utime(override, ns=(0, 10**9))

    assert load_config("budget", settings)["recognition_per_minute"] == 9


def test_a_file_of_a_new_size_is_read_again_whatever_its_timestamp_says(
    settings: Settings,
) -> None:
    settings.config_dir.mkdir(parents=True)
    override = settings.config_dir / "budget.json"
    override.write_text(json.dumps({"recognition_per_minute": 2}), encoding="utf-8")
    assert load_config("budget", settings)["recognition_per_minute"] == 2

    _write_keeping_the_timestamp(override, json.dumps({"recognition_per_minute": 1234}))

    assert load_config("budget", settings)["recognition_per_minute"] == 1234


def test_what_one_caller_edits_does_not_change_what_the_next_one_reads(
    settings: Settings,
) -> None:
    first = load_config("budget", settings)

    first["recognition_per_minute"] = 1

    assert load_config("budget", settings)["recognition_per_minute"] == 60


# --- writing and removing overrides ----------------------------------------


def test_a_stored_override_answers_in_place_of_the_shipped_file(settings: Settings) -> None:
    write_override("budget", {"recognition_per_minute": 2}, settings)

    assert load_config("budget", settings) == {"recognition_per_minute": 2}


def test_a_second_store_is_seen_even_inside_one_clock_tick(settings: Settings) -> None:
    """Two loads of the same set must not serve the first one's configuration."""
    path = write_override("budget", {"recognition_per_minute": 20}, settings)
    assert load_config("budget", settings)["recognition_per_minute"] == 20
    stamp = path.stat()

    write_override("budget", {"recognition_per_minute": 99}, settings)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    assert load_config("budget", settings)["recognition_per_minute"] == 99


def test_storing_the_same_override_twice_leaves_the_same_bytes(settings: Settings) -> None:
    path = write_override("budget", {"recognition_per_minute": 2}, settings)
    first = path.read_text(encoding="utf-8")

    write_override("budget", {"recognition_per_minute": 2}, settings)

    assert path.read_text(encoding="utf-8") == first


def test_only_the_files_this_service_owns_may_be_stored(settings: Settings) -> None:
    with pytest.raises(ValueError, match="not a configuration file"):
        write_override("passwords", {"anything": True}, settings)


def test_removing_the_overrides_names_what_it_removed(settings: Settings) -> None:
    write_override("budget", {"recognition_per_minute": 2}, settings)

    assert remove_overrides(settings) == ["budget.json"]
    assert load_config("budget", settings)["recognition_per_minute"] == 60


def test_removing_the_overrides_when_there_are_none_is_not_an_error(
    settings: Settings,
) -> None:
    assert remove_overrides(settings) == []
