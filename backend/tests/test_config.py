from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import ConfigError, load_config, resolve_path
from app.settings import Settings, load_settings


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
    with pytest.raises(ConfigError) as raised:
        load_config("languages", settings)

    assert "languages.json" in str(raised.value)
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
