"""Translating recognized text through the cache.

Sarvam is faked by respx, so every provider call this file counts is a call the
service really made and none of them leaves the machine (`qa_notes`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace

import httpx
import pytest
import respx

from app.config import load_config, write_override
from app.errors import ApiError
from app.logging_setup import configure_logging
from app.main import create_app
from app.settings import Settings
from app.translation import Translator
from app.translation_cache import DEFAULT_LIFETIME_SECONDS, TranslationCache

TRANSLATE_URL = "https://api.sarvam.ai/translate"

HEADLINE = "കേരളത്തിൽ മഴ തുടരുന്നു"
ENGLISH = "Rain continues in Kerala"
OTHER_HEADLINE = "തിരുവനന്തപുരത്ത് ഇന്ന് അവധി"


class Clock:
    """A clock that moves only when a test says so."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def sarvam() -> Iterator[respx.MockRouter]:
    with respx.mock:
        yield respx.mock


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def cache(clock: Clock) -> TranslationCache:
    return TranslationCache(monotonic=clock)


@pytest.fixture
def translator(settings: Settings, cache: TranslationCache) -> Translator:
    return Translator(settings, cache=cache)


def route_translate(translated: str = ENGLISH) -> respx.Route:
    return respx.post(TRANSLATE_URL).mock(
        return_value=httpx.Response(200, json={"translated_text": translated})
    )


def write_languages(settings: Settings, payload: dict) -> None:
    """Change the configuration in force, the way the admin endpoint does."""
    write_override("languages", payload, settings)


def malayalam_mapped_to(entry: str) -> dict:
    """The shipped configuration, with Malayalam's translation remapped."""
    return {
        "sources": [
            {
                "code": "ml-IN",
                "name": "Malayalam",
                "recognition_provider": "sarvam-parse",
                "translation_provider": entry,
            }
        ],
        "targets": [{"code": "en-IN", "name": "English"}],
        "providers": {
            "sarvam-parse": {"kind": "sarvam_parse"},
            "sarvam-translate": {"kind": "sarvam_translate", "model": "mayura:v1"},
            "sarvam-translate-alt": {
                "kind": "sarvam_translate",
                "model": "sarvam-translate:v1",
            },
        },
    }


def two_sources_sharing_one_provider() -> dict:
    """Malayalam and Hindi, both translated by the same provider entry.

    One entry for both languages is what leaves the source language as the
    only thing separating their cache entries.
    """
    return {
        "sources": [
            {
                "code": code,
                "name": name,
                "recognition_provider": "sarvam-parse",
                "translation_provider": "sarvam-translate",
            }
            for code, name in (("ml-IN", "Malayalam"), ("hi-IN", "Hindi"))
        ],
        "targets": [{"code": "en-IN", "name": "English"}],
        "providers": {
            "sarvam-parse": {"kind": "sarvam_parse"},
            "sarvam-translate": {"kind": "sarvam_translate", "model": "mayura:v1"},
        },
    }


def lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.strip().splitlines() if line.strip()]


async def translate(translator: Translator, text: str = HEADLINE):
    return await translator.translate(text, source_language="ml-IN", target_language="en-IN")


# --- Translating -----------------------------------------------------------


async def test_recognized_text_comes_back_translated(translator: Translator) -> None:
    route_translate()

    answer = await translate(translator)

    assert answer.text == ENGLISH
    assert answer.cached is False
    assert answer.provider == "sarvam-translate"


async def test_the_provider_configuration_maps_the_language_to_is_the_one_called(
    translator: Translator,
) -> None:
    route = route_translate()

    await translate(translator)

    assert json.loads(route.calls.last.request.content)["model"] == "mayura:v1"


async def test_text_with_nothing_in_it_is_answered_with_nothing(
    translator: Translator,
) -> None:
    """ST-10's blank wall: no provider is called, and no configuration is read."""
    answer = await translate(translator, "  \n  ")

    assert answer.text == ""
    assert answer.provider is None
    assert not respx.calls


# --- The same headline seen again (ST-5) -----------------------------------


async def test_the_same_text_again_is_answered_without_a_provider_call(
    translator: Translator,
) -> None:
    """ST-5: three refresh cycles on one headline, one translation call."""
    route = route_translate()

    first = await translate(translator)
    second = await translate(translator)
    third = await translate(translator)

    assert route.call_count == 1
    assert [answer.text for answer in (first, second, third)] == [ENGLISH] * 3
    assert [answer.cached for answer in (first, second, third)] == [False, True, True]


async def test_the_same_headline_split_differently_is_still_a_cache_hit(
    translator: Translator,
) -> None:
    """Recognition joins its blocks with newlines, and may split them again."""
    route = route_translate()

    await translate(translator, f"{HEADLINE}\nരണ്ടാം വരി")
    answer = await translate(translator, f"{HEADLINE}   രണ്ടാം വരി")

    assert route.call_count == 1
    assert answer.cached is True


async def test_a_different_headline_is_translated_on_its_own(
    translator: Translator,
) -> None:
    """The headline changes, so the next cycle misses the cache."""
    route = route_translate()

    await translate(translator)
    answer = await translate(translator, OTHER_HEADLINE)

    assert route.call_count == 2
    assert answer.cached is False


async def test_the_same_text_read_as_another_source_language_is_translated_again(
    translator: Translator, settings: Settings
) -> None:
    """Both languages share one provider entry, so only the source separates them."""
    write_languages(settings, two_sources_sharing_one_provider())
    route = route_translate()

    await translator.translate(HEADLINE, source_language="ml-IN", target_language="en-IN")
    answer = await translator.translate(HEADLINE, source_language="hi-IN", target_language="en-IN")

    assert route.call_count == 2
    assert answer.cached is False


async def test_a_cache_hit_is_said_in_the_log(
    translator: Translator, capsys: pytest.CaptureFixture[str]
) -> None:
    """ST-5 is a verdict read from this line."""
    route_translate()
    configure_logging()
    await translate(translator)
    capsys.readouterr()

    await translate(translator)

    events = [line["event"] for line in lines(capsys.readouterr().out)]
    assert events == ["translation.cache_hit"]


async def test_an_entry_past_its_lifetime_is_translated_again(
    translator: Translator, clock: Clock
) -> None:
    route = route_translate()

    await translate(translator)
    clock.advance(DEFAULT_LIFETIME_SECONDS + 1.0)
    answer = await translate(translator)

    assert route.call_count == 2
    assert answer.cached is False


async def test_a_failed_translation_is_not_remembered(translator: Translator) -> None:
    """A provider error must not become the answer for the next ten minutes."""
    respx.post(TRANSLATE_URL).mock(return_value=httpx.Response(503, text="busy"))

    with pytest.raises(ApiError):
        await translate(translator)

    route_translate()
    answer = await translate(translator)
    assert answer.text == ENGLISH
    assert answer.cached is False


# --- A provider change takes effect on the next request (ST-8) -------------


async def test_remapping_the_language_changes_the_provider_on_the_next_request(
    translator: Translator, settings: Settings
) -> None:
    """ST-8, and why the provider entry's name is part of the cache key."""
    route = route_translate()
    first = await translate(translator)

    write_languages(settings, malayalam_mapped_to("sarvam-translate-alt"))
    second = await translate(translator)

    assert first.provider == "sarvam-translate"
    assert second.provider == "sarvam-translate-alt"
    assert second.cached is False, "the new entry does not inherit the old one's answers"
    assert route.call_count == 2
    assert json.loads(route.calls.last.request.content)["model"] == "sarvam-translate:v1"


async def test_a_language_taken_out_of_configuration_is_refused(
    translator: Translator, settings: Settings
) -> None:
    write_languages(settings, {"sources": [], "targets": [], "providers": {}})

    with pytest.raises(ApiError) as raised:
        await translate(translator)

    assert raised.value.status_code == 400
    assert raised.value.code == "unsupported_language"
    assert "ml-IN" in raised.value.message
    assert not respx.calls


async def test_a_language_configuration_the_service_cannot_read_is_an_internal_error(
    translator: Translator, settings: Settings
) -> None:
    """Only a file edited past the admin endpoint can get here."""
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "languages.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ApiError) as raised:
        await translate(translator)

    assert raised.value.status_code == 500
    assert raised.value.code == "invalid_configuration"


# --- How long an answer is kept --------------------------------------------


def test_the_lifetime_is_what_the_budget_file_says(
    translator: Translator, settings: Settings
) -> None:
    budget = load_config("budget", settings)
    budget["translation_cache_seconds"] = 42
    write_override("budget", budget, settings)

    assert translator.lifetime_seconds() == 42.0


def test_a_budget_file_without_the_field_keeps_the_default(
    translator: Translator, settings: Settings
) -> None:
    """The system test data loader's low-budget set does not name a lifetime."""
    write_override(
        "budget",
        {"recognition_per_minute": 2, "translation_per_minute": 60, "max_wait_seconds": 15},
        settings,
    )

    assert translator.lifetime_seconds() == DEFAULT_LIFETIME_SECONDS


def test_a_lifetime_that_is_not_a_number_of_seconds_is_said_and_ignored(
    translator: Translator, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    budget = load_config("budget", settings)
    budget["translation_cache_seconds"] = "ten minutes"
    write_override("budget", budget, settings)
    configure_logging()
    capsys.readouterr()

    assert translator.lifetime_seconds() == DEFAULT_LIFETIME_SECONDS

    (line,) = lines(capsys.readouterr().out)
    assert line["event"] == "config.invalid"
    assert line["field"] == "translation_cache_seconds"


async def test_switching_the_cache_off_translates_every_time(
    translator: Translator, settings: Settings
) -> None:
    budget = load_config("budget", settings)
    budget["translation_cache_seconds"] = 0
    write_override("budget", budget, settings)
    route = route_translate()

    await translate(translator)
    await translate(translator)

    assert route.call_count == 2


# --- One cache per process -------------------------------------------------


async def test_a_second_translator_has_a_cache_of_its_own(
    settings: Settings, cache: TranslationCache
) -> None:
    """D7: the cache is this process's memory, so a second instance repeats the call."""
    route = route_translate()

    await translate(Translator(settings, cache=cache))
    await translate(Translator(settings, cache=TranslationCache()))

    assert route.call_count == 2


def test_an_app_is_built_with_a_translator_of_its_own(settings: Settings) -> None:
    first = create_app(settings)
    second = create_app(replace(settings))

    assert first.state.translator is not second.state.translator
