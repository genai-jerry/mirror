"""Which recognition client answers for a language, as configuration says now."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import write_override
from app.errors import ApiError
from app.providers.sarvam_parse import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)
from app.recognition import recognition_client_for
from app.settings import Settings


def languages_file(settings: Settings, **providers: Any) -> None:
    """A whole languages file in which Malayalam names its recognition entry."""
    entries: dict[str, Any] = {
        "sarvam-translate": {"kind": "sarvam_translate", "model": "mayura:v1"},
        **(providers or {"sarvam-parse": {"kind": "sarvam_parse"}}),
    }
    recognition = next(name for name in entries if name != "sarvam-translate")
    write_override(
        "languages",
        {
            "sources": [
                {
                    "code": "ml-IN",
                    "name": "Malayalam",
                    "recognition_provider": recognition,
                    "translation_provider": "sarvam-translate",
                }
            ],
            "targets": [{"code": "en-IN", "name": "English"}],
            "providers": entries,
        },
        settings,
    )


def test_the_client_is_the_entry_the_configuration_names(settings: Settings) -> None:
    client = recognition_client_for("ml-IN", settings)

    assert client.provider_name == "sarvam-parse"
    assert client.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert client.poll_interval_seconds == DEFAULT_POLL_INTERVAL_SECONDS


def test_the_language_code_is_matched_without_regard_to_case(settings: Settings) -> None:
    assert recognition_client_for("ML-in", settings).provider_name == "sarvam-parse"


def test_the_entrys_own_timings_come_with_it(settings: Settings) -> None:
    """The design's 12 seconds and 1 second are configuration, not code."""
    patient = {"kind": "sarvam_parse", "timeout_seconds": 30, "poll_interval_seconds": 2}
    languages_file(settings, **{"sarvam-parse-patient": patient})

    client = recognition_client_for("ml-IN", settings)

    assert client.provider_name == "sarvam-parse-patient"
    assert client.timeout_seconds == 30.0
    assert client.poll_interval_seconds == 2.0


def test_a_remapped_language_is_read_by_the_next_call(settings: Settings) -> None:
    assert recognition_client_for("ml-IN", settings).provider_name == "sarvam-parse"

    languages_file(settings, **{"sarvam-parse-alt": {"kind": "sarvam_parse"}})

    assert recognition_client_for("ml-IN", settings).provider_name == "sarvam-parse-alt"


def test_a_language_the_configuration_does_not_offer_is_refused(settings: Settings) -> None:
    with pytest.raises(ApiError) as raised:
        recognition_client_for("fr-FR", settings)

    assert raised.value.status_code == 400
    assert raised.value.code == "unsupported_language"
    assert raised.value.message == "source language fr-FR is not configured"


def test_an_entry_of_the_wrong_kind_is_a_provider_error(settings: Settings) -> None:
    """An operator who points recognition at a translation entry is told so."""
    languages_file(settings, **{"sarvam-translate-alt": {"kind": "sarvam_translate"}})

    with pytest.raises(ApiError) as raised:
        recognition_client_for("ml-IN", settings)

    assert raised.value.status_code == 502
    assert raised.value.code == "provider_error"


def test_a_configuration_that_cannot_be_read_is_refused(settings: Settings) -> None:
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "languages.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ApiError) as raised:
        recognition_client_for("ml-IN", settings)

    assert raised.value.status_code == 500
    assert raised.value.code == "invalid_configuration"
    assert "languages.json" not in raised.value.message, "the caller is not told about our files"
