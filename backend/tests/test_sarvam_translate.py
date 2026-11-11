"""The Sarvam translation client, with Sarvam faked by respx.

Not one test here reaches the real provider: every route is declared, so an
undeclared call fails the test rather than leaving the factory's runner to call
Sarvam for real (`qa_notes`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace

import httpx
import pytest
import respx

from app.errors import ApiError
from app.languages import Provider
from app.logging_setup import configure_logging, set_request_id
from app.providers.sarvam_translate import (
    API_KEY_HEADER,
    DEFAULT_INPUT_LIMIT,
    MODEL_INPUT_LIMITS,
    SarvamTranslateClient,
)
from app.settings import Settings

TRANSLATE_URL = "https://api.sarvam.ai/translate"

HEADLINE = "കേരളത്തിൽ മഴ തുടരുന്നു"
ENGLISH = "Rain continues in Kerala"

MAYURA = Provider(name="sarvam-translate", kind="sarvam_translate", model="mayura:v1")
ALTERNATE = Provider(
    name="sarvam-translate-alt", kind="sarvam_translate", model="sarvam-translate:v1"
)


@pytest.fixture(autouse=True)
def sarvam() -> Iterator[respx.MockRouter]:
    """Sarvam is mocked for every test in this file; an undeclared call fails."""
    with respx.mock:
        yield respx.mock


@pytest.fixture
def translator(settings: Settings) -> SarvamTranslateClient:
    return SarvamTranslateClient.from_provider(MAYURA, settings)


def route_translate(translated: str = ENGLISH) -> respx.Route:
    return respx.post(TRANSLATE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "translated_text": translated,
                "source_language_code": "ml-IN",
                "request_id": "req-sarvam-1",
            },
        )
    )


def sent(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content)


def lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.strip().splitlines() if line.strip()]


async def translate(client: SarvamTranslateClient, text: str = HEADLINE) -> str:
    return await client.translate(text, source_language="ml-IN", target_language="en-IN")


# --- The call --------------------------------------------------------------


async def test_the_translation_is_what_sarvam_answered(
    translator: SarvamTranslateClient,
) -> None:
    route_translate()

    assert await translate(translator) == ENGLISH


async def test_the_request_carries_the_text_the_languages_and_the_model(
    translator: SarvamTranslateClient,
) -> None:
    route = route_translate()

    await translate(translator)

    assert sent(route) == {
        "input": HEADLINE,
        "source_language_code": "ml-IN",
        "target_language_code": "en-IN",
        "model": "mayura:v1",
    }


async def test_the_key_goes_in_the_header_and_nowhere_else(
    translator: SarvamTranslateClient,
) -> None:
    route = route_translate()

    await translate(translator)

    request = route.calls.last.request
    assert request.headers[API_KEY_HEADER] == "test-key"
    assert "test-key" not in request.content.decode("utf-8")


async def test_the_model_of_the_provider_entry_is_the_model_that_is_asked(
    settings: Settings,
) -> None:
    """ST-8: remapping a language to the alternate entry changes the call."""
    route = route_translate()
    client = SarvamTranslateClient.from_provider(ALTERNATE, settings)

    await translate(client)

    assert sent(route)["model"] == "sarvam-translate:v1"


async def test_an_entry_with_no_model_asks_for_none(settings: Settings) -> None:
    """Sarvam's own default answers; this service does not invent a model."""
    route = route_translate()
    client = SarvamTranslateClient.from_provider(
        replace(MAYURA, model=None),
        settings,
    )

    await translate(client)

    assert "model" not in sent(route)


async def test_text_with_nothing_in_it_is_not_sent_anywhere(
    translator: SarvamTranslateClient,
) -> None:
    """The blank wall of the contract: nothing recognized, nothing translated."""
    assert await translate(translator, "   \n ") == ""
    assert not respx.calls


def test_a_recognition_entry_cannot_translate(settings: Settings) -> None:
    """A language mapped to the wrong kind of entry is a configuration mistake."""
    with pytest.raises(ApiError) as raised:
        SarvamTranslateClient.from_provider(
            Provider(name="sarvam-parse", kind="sarvam_parse"), settings
        )

    assert raised.value.status_code == 502
    assert raised.value.code == "provider_error"
    assert "sarvam-parse" in raised.value.message


# --- Longer than the model takes -------------------------------------------


def test_each_model_has_the_cap_sarvam_documents() -> None:
    assert MODEL_INPUT_LIMITS["mayura:v1"] == 1000
    assert MODEL_INPUT_LIMITS["sarvam-translate:v1"] == 2000


def test_a_model_this_service_has_not_heard_of_gets_the_smaller_cap(
    settings: Settings,
) -> None:
    client = SarvamTranslateClient.from_provider(replace(MAYURA, model="something:v9"), settings)

    assert client.input_limit == DEFAULT_INPUT_LIMIT


async def test_text_past_the_cap_is_cut_to_it(translator: SarvamTranslateClient) -> None:
    route = route_translate()

    await translate(translator, "ക" * 1500)

    assert len(sent(route)["input"]) == 1000


async def test_the_alternate_model_takes_twice_as_much(settings: Settings) -> None:
    route = route_translate()
    client = SarvamTranslateClient.from_provider(ALTERNATE, settings)

    await translate(client, "ക" * 2500)

    assert len(sent(route)["input"]) == 2000


async def test_cutting_the_text_is_said_once_in_the_log(
    translator: SarvamTranslateClient, capsys: pytest.CaptureFixture[str]
) -> None:
    route_translate()
    configure_logging()
    capsys.readouterr()

    await translate(translator, "ക" * 1500)

    truncated = [
        line for line in lines(capsys.readouterr().out) if line["event"] == "translation.truncated"
    ]
    assert len(truncated) == 1
    assert truncated[0]["level"] == "warning"
    assert truncated[0]["limit"] == 1000
    assert truncated[0]["characters"] == 1500


# --- What the log says -----------------------------------------------------


async def test_the_translation_call_is_logged_with_its_provider_entry(
    translator: SarvamTranslateClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """The design's logged-events table is what ST-5 and ST-8 read."""
    route_translate()
    configure_logging()
    set_request_id("req-1")
    capsys.readouterr()

    await translate(translator)

    (line,) = lines(capsys.readouterr().out)
    assert line["event"] == "translation.call"
    assert line["provider"] == "sarvam-translate"
    assert line["model"] == "mayura:v1"
    assert line["request_id"] == "req-1"


async def test_the_key_appears_in_no_log_line(
    translator: SarvamTranslateClient, capsys: pytest.CaptureFixture[str]
) -> None:
    route_translate()
    configure_logging()
    capsys.readouterr()

    await translate(translator)

    assert "test-key" not in capsys.readouterr().out


# --- When it goes wrong ----------------------------------------------------


async def test_no_api_key_is_a_provider_error(settings: Settings) -> None:
    client = SarvamTranslateClient.from_provider(MAYURA, replace(settings, sarvam_api_key=None))

    with pytest.raises(ApiError) as raised:
        await translate(client)

    assert raised.value.status_code == 502
    assert raised.value.code == "provider_error"
    assert not respx.calls, "nothing is sent without a key"


@pytest.mark.parametrize("status", [400, 429, 500, 503])
async def test_a_failure_from_sarvam_is_a_provider_error(
    translator: SarvamTranslateClient, status: int
) -> None:
    respx.post(TRANSLATE_URL).mock(return_value=httpx.Response(status, text="no"))

    with pytest.raises(ApiError) as raised:
        await translate(translator)

    assert raised.value.status_code == 502
    assert raised.value.code == "provider_error"
    assert raised.value.log_fields["provider_status"] == status


async def test_sarvam_not_answering_in_time_is_a_provider_error(
    translator: SarvamTranslateClient,
) -> None:
    """The app does the same thing about any failure: keep the overlay it has."""
    respx.post(TRANSLATE_URL).mock(side_effect=httpx.ReadTimeout("too slow"))

    with pytest.raises(ApiError) as raised:
        await translate(translator)

    assert raised.value.status_code == 502
    assert raised.value.log_fields["reason"] == "timeout"


async def test_sarvam_being_unreachable_is_a_provider_error(
    translator: SarvamTranslateClient,
) -> None:
    respx.post(TRANSLATE_URL).mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(ApiError) as raised:
        await translate(translator)

    assert raised.value.status_code == 502
    assert raised.value.log_fields["reason"] == "ConnectError"


async def test_an_answer_that_is_not_json_is_a_provider_error(
    translator: SarvamTranslateClient,
) -> None:
    respx.post(TRANSLATE_URL).mock(return_value=httpx.Response(200, text="<html>"))

    with pytest.raises(ApiError) as raised:
        await translate(translator)

    assert raised.value.code == "provider_error"
    assert raised.value.log_fields["reason"] == "unreadable_body"


async def test_an_answer_with_no_translation_is_a_provider_error(
    translator: SarvamTranslateClient,
) -> None:
    respx.post(TRANSLATE_URL).mock(return_value=httpx.Response(200, json={"request_id": "r-1"}))

    with pytest.raises(ApiError) as raised:
        await translate(translator)

    assert raised.value.log_fields["reason"] == "no_translated_text"
