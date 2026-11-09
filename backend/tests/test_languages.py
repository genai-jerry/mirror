from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from conftest import APP_TOKEN
from fastapi.testclient import TestClient

from app.config import ConfigError
from app.languages import (
    LanguageConfig,
    load_language_config,
    parse_language_config,
)
from app.logging_setup import configure_logging
from app.main import create_app
from app.settings import Settings

SHIPPED_ANSWER = {
    "sources": [{"code": "ml-IN", "name": "Malayalam"}],
    "targets": [{"code": "en-IN", "name": "English"}],
}

WITH_TAMIL: dict[str, Any] = {
    "sources": [
        {
            "code": "ml-IN",
            "name": "Malayalam",
            "recognition_provider": "sarvam-parse",
            "translation_provider": "sarvam-translate",
        },
        {
            "code": "ta-IN",
            "name": "Tamil",
            "recognition_provider": "sarvam-parse",
            "translation_provider": "sarvam-translate",
        },
    ],
    "targets": [{"code": "en-IN", "name": "English"}],
    "providers": {
        "sarvam-parse": {"kind": "sarvam_parse"},
        "sarvam-translate": {"kind": "sarvam_translate", "model": "mayura:v1"},
    },
}


def _write_override(settings: Settings, payload: Any) -> Path:
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    path = settings.config_dir / "languages.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --- GET /v1/languages ------------------------------------------------------


def test_the_endpoint_lists_the_shipped_languages(client: TestClient) -> None:
    response = client.get("/v1/languages")

    assert response.status_code == 200
    assert response.json() == SHIPPED_ANSWER


def test_the_answer_keeps_the_providers_in_the_backend(client: TestClient) -> None:
    """The picker needs codes and names; which provider serves a language is ours."""
    assert "provider" not in client.get("/v1/languages").text
    assert "sarvam" not in client.get("/v1/languages").text


def test_a_language_added_in_configuration_needs_no_restart(
    client: TestClient, settings: Settings
) -> None:
    """The backend half of ST-7: an operator adds Tamil, the list grows."""
    assert client.get("/v1/languages").json() == SHIPPED_ANSWER

    _write_override(settings, WITH_TAMIL)

    assert client.get("/v1/languages").json() == {
        "sources": [
            {"code": "ml-IN", "name": "Malayalam"},
            {"code": "ta-IN", "name": "Tamil"},
        ],
        "targets": [{"code": "en-IN", "name": "English"}],
    }


def test_removing_the_override_restores_the_shipped_list(
    client: TestClient, settings: Settings
) -> None:
    override = _write_override(settings, WITH_TAMIL)
    assert len(client.get("/v1/languages").json()["sources"]) == 2

    override.unlink()

    assert client.get("/v1/languages").json() == SHIPPED_ANSWER


def test_an_empty_configuration_answers_with_empty_lists(
    client: TestClient, settings: Settings
) -> None:
    """A service that offers nothing yet still answers — the picker shows nothing."""
    _write_override(settings, {})

    response = client.get("/v1/languages")

    assert response.status_code == 200
    assert response.json() == {"sources": [], "targets": []}


@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"sources": "ml-IN"}, id="sources is not a list"),
        pytest.param(
            {"sources": [{"code": "ml-IN", "name": "Malayalam"}]},
            id="a source names no provider",
        ),
    ],
)
def test_a_configuration_the_service_cannot_use_answers_in_the_one_shape(
    client: TestClient, settings: Settings, override: dict[str, Any]
) -> None:
    """Only a hand-edited file gets here; the admin endpoint refuses these."""
    _write_override(settings, override)

    response = client.get("/v1/languages")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "invalid_configuration",
            "message": "The backend's language configuration cannot be read.",
        }
    }


def test_a_file_that_is_not_json_answers_in_the_one_shape(
    client: TestClient, settings: Settings
) -> None:
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "languages.json").write_text("{not json", encoding="utf-8")

    response = client.get("/v1/languages")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "invalid_configuration"
    assert "languages.json" not in response.text, "the caller is not told about our files"


def test_the_reason_a_configuration_was_refused_is_logged(
    client: TestClient, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_override(settings, {"sources": "ml-IN"})
    # The app was built before this test began, so its handler holds the
    # standard output of that moment; point the logger at this test's.
    configure_logging()
    capsys.readouterr()

    client.get("/v1/languages")

    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    invalid = [line for line in lines if line["event"] == "config.invalid"]
    assert invalid, "an operator needs to know which file is wrong and why"
    assert invalid[0]["name"] == "languages"
    assert "sources must be a JSON list" in invalid[0]["message"]


# --- the optional app token (D10) ------------------------------------------


def test_the_endpoint_is_open_when_no_app_token_is_set(client: TestClient) -> None:
    assert client.get("/v1/languages").status_code == 200


def test_the_app_token_is_required_once_it_is_set(settings: Settings) -> None:
    with TestClient(create_app(replace(settings, app_token=APP_TOKEN))) as client:
        response = client.get("/v1/languages")

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthorized", "message": "This endpoint needs the app token."}
    }


@pytest.mark.parametrize(
    "header",
    [
        pytest.param({}, id="no header"),
        pytest.param({"Authorization": "Bearer not-the-token"}, id="the wrong token"),
        pytest.param({"Authorization": "Bearer "}, id="an empty token"),
        pytest.param({"Authorization": APP_TOKEN}, id="no scheme"),
        pytest.param({"Authorization": f"Basic {APP_TOKEN}"}, id="the wrong scheme"),
    ],
)
def test_the_app_token_has_to_be_a_bearer_token(settings: Settings, header: dict[str, str]) -> None:
    with TestClient(create_app(replace(settings, app_token=APP_TOKEN))) as client:
        assert client.get("/v1/languages", headers=header).status_code == 401


def test_the_right_app_token_is_let_through(settings: Settings) -> None:
    with TestClient(create_app(replace(settings, app_token=APP_TOKEN))) as client:
        response = client.get("/v1/languages", headers={"Authorization": f"Bearer {APP_TOKEN}"})

    assert response.status_code == 200
    assert response.json() == SHIPPED_ANSWER


def test_a_refused_call_does_not_echo_the_token(settings: Settings) -> None:
    with TestClient(create_app(replace(settings, app_token=APP_TOKEN))) as client:
        response = client.get("/v1/languages", headers={"Authorization": "Bearer guess"})

    assert APP_TOKEN not in response.text


# --- the provider mapping (the "Provider changed for a language" scenario) ---


def test_the_providers_for_a_language_come_from_configuration(settings: Settings) -> None:
    config = load_language_config(settings)

    recognition = config.recognition_provider_for("ml-IN")
    translation = config.translation_provider_for("ml-IN")

    assert recognition.name == "sarvam-parse"
    assert recognition.kind == "sarvam_parse"
    assert translation.name == "sarvam-translate"
    assert translation.model == "mayura:v1"


def test_a_changed_provider_is_used_from_the_next_read(settings: Settings) -> None:
    """ST-8: remap Malayalam translation, and the next request uses the new entry."""
    assert load_language_config(settings).translation_provider_for("ml-IN").name == (
        "sarvam-translate"
    )
    shipped = json.loads((settings.defaults_dir / "languages.json").read_text(encoding="utf-8"))
    shipped["sources"][0]["translation_provider"] = "sarvam-translate-alt"
    _write_override(settings, shipped)

    translation = load_language_config(settings).translation_provider_for("ml-IN")

    assert translation.name == "sarvam-translate-alt"
    assert translation.model == "sarvam-translate:v1"


def test_the_shipped_file_offers_the_alternate_translation_entry(settings: Settings) -> None:
    """ST-8 needs a second configured entry to switch to without a code change."""
    assert "sarvam-translate-alt" in load_language_config(settings).providers


def test_an_unconfigured_language_is_named_when_a_provider_is_asked_for(
    settings: Settings,
) -> None:
    with pytest.raises(ConfigError, match="fr-FR"):
        load_language_config(settings).recognition_provider_for("fr-FR")


def test_a_pair_is_supported_only_when_both_halves_are_configured(
    settings: Settings,
) -> None:
    config = load_language_config(settings)

    assert config.supports("ml-IN", "en-IN")
    assert not config.supports("fr-FR", "en-IN")
    assert not config.supports("ml-IN", "fr-FR")


def test_a_code_is_matched_without_regard_to_case(settings: Settings) -> None:
    """BCP-47 codes are case-insensitive, so `ML-in` is the language `ml-IN`."""
    config = load_language_config(settings)

    found = config.source("ML-in")

    assert found is not None
    assert found.code == "ml-IN", "the configured spelling is the one we answer with"


# --- what the parser refuses ------------------------------------------------


def test_a_configuration_with_nothing_in_it_is_allowed() -> None:
    config = parse_language_config({})

    assert config == LanguageConfig()
    assert config.picker_payload() == {"sources": [], "targets": []}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            {
                "sources": [
                    {
                        "code": "ml-IN",
                        "name": "Malayalam",
                        "recognition_provider": "no-such-provider",
                        "translation_provider": "sarvam-translate",
                    }
                ],
                "providers": {"sarvam-translate": {"kind": "sarvam_translate"}},
            },
            "not in providers",
            id="a source names a provider that is not configured",
        ),
        pytest.param(
            {
                "sources": [
                    {
                        "code": "ml-IN",
                        "name": "Malayalam",
                        "recognition_provider": "p",
                        "translation_provider": "p",
                    },
                    {
                        "code": "ML-in",
                        "name": "Malayalam again",
                        "recognition_provider": "p",
                        "translation_provider": "p",
                    },
                ],
                "providers": {"p": {"kind": "sarvam_parse"}},
            },
            "configured twice",
            id="the same language twice, spelled differently",
        ),
        pytest.param(
            {"targets": [{"code": "en-IN"}]},
            "needs a non-empty name",
            id="a target language with no name",
        ),
        pytest.param(
            {"targets": [{"code": " ", "name": "English"}]},
            "needs a non-empty code",
            id="a target language with a blank code",
        ),
        pytest.param(
            {"targets": {"code": "en-IN"}}, "must be a JSON list", id="targets is an object"
        ),
        pytest.param(
            {"sources": ["ml-IN"]}, "must be a JSON object", id="a source is a bare string"
        ),
        pytest.param({"providers": []}, "must be a JSON object", id="providers is a list"),
        pytest.param(
            {"providers": {"sarvam-parse": {"model": "mayura:v1"}}},
            "needs a non-empty kind",
            id="a provider with no kind",
        ),
        pytest.param(
            {"providers": {"sarvam-parse": {"kind": "sarvam_parse", "model": 7}}},
            "needs a non-empty model",
            id="a provider whose model is not text",
        ),
    ],
)
def test_the_parser_says_what_is_wrong(raw: dict[str, Any], expected: str) -> None:
    with pytest.raises(ConfigError, match=expected):
        parse_language_config(raw)


def test_the_shipped_file_is_one_the_parser_accepts(settings: Settings) -> None:
    """Whatever else changes, the file the service ships with must be usable."""
    config = load_language_config(settings)

    assert config.picker_payload() == SHIPPED_ANSWER
