"""`POST /v1/frames/translate`, end to end, with Sarvam faked by respx.

Every status code of the API contract is proved here against faked providers,
and so are the two things the system test cases read the log for: a request in
a language the service does not offer costs no provider call at all (ST-9), and
the same headline again costs no translation call (ST-5).

Not one test reaches the real provider: every route is declared, so an
undeclared call fails the test rather than leaving the factory's runner to call
Sarvam for real (`qa_notes`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
import respx
from conftest import APP_TOKEN
from fastapi.testclient import TestClient

from app.budget import recognition_budget
from app.config import write_override
from app.logging_setup import configure_logging
from app.main import create_app
from app.settings import Settings
from app.translation_cache import normalise
from app.uploads import MAX_IMAGE_BYTES
from tests.test_images import png
from tests.test_sarvam_parse import (
    HEADLINE,
    PARSE_URL,
    SUBHEAD,
    parse_output,
    route_sarvam,
)
from tests.test_sarvam_translate import ENGLISH, TRANSLATE_URL, route_translate
from tests.test_uploads import padded

PATH = "/v1/frames/translate"

#: The two blocks of `HEADLINE_BLOCKS` sit inside this crop, so the region hint
#: is their union as fractions of it: x 80/1000, y 205/500, and so on.
CROP = png(1000, 500)
REGION = {"x": 0.08, "y": 0.41, "width": 0.84, "height": 0.27}
RECOGNIZED = f"{HEADLINE}\n{SUBHEAD}"

OTHER_HEADLINE = "തിരുവനന്തപുരത്ത് ഇന്ന് അവധി"
OTHER_ENGLISH = "Holiday in Thiruvananthapuram today"


@pytest.fixture(autouse=True)
def sarvam() -> Iterator[respx.MockRouter]:
    """Sarvam is mocked for every test in this file; an undeclared call fails."""
    with respx.mock:
        yield respx.mock


def post(
    client: TestClient,
    *,
    image: bytes = CROP,
    source_language: str = "ml-IN",
    target_language: str = "en-IN",
    **kwargs: Any,
) -> Any:
    return client.post(
        PATH,
        files={"image": ("crop.png", image, "image/png")},
        data={"source_language": source_language, "target_language": target_language},
        **kwargs,
    )


def budget_file(settings: Settings, **fields: Any) -> None:
    """A whole budget file in the override directory, as an operator would write it."""
    write_override(
        "budget",
        {
            "recognition_per_minute": 60,
            "translation_per_minute": 30,
            "max_wait_seconds": 15,
            **fields,
        },
        settings,
    )


def languages_file(settings: Settings, *, parse: dict[str, Any] | None = None) -> None:
    """A whole languages file: Malayalam to English, with the entries named."""
    write_override(
        "languages",
        {
            "sources": [
                {
                    "code": "ml-IN",
                    "name": "Malayalam",
                    "recognition_provider": "sarvam-parse",
                    "translation_provider": "sarvam-translate",
                }
            ],
            "targets": [{"code": "en-IN", "name": "English"}],
            "providers": {
                "sarvam-parse": {"kind": "sarvam_parse", **(parse or {})},
                "sarvam-translate": {"kind": "sarvam_translate", "model": "mayura:v1"},
            },
        },
        settings,
    )


def calls_to(url: str) -> int:
    return sum(1 for call in respx.calls if str(call.request.url) == url)


def lines(captured: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in captured.strip().splitlines() if line.strip()]


def events(captured: str) -> list[str]:
    return [line["event"] for line in lines(captured)]


# --- The 200 of the contract ------------------------------------------------


def test_a_frame_comes_back_with_its_text_translation_and_region(
    client: TestClient,
) -> None:
    route_sarvam()
    route_translate()

    response = post(client)

    assert response.status_code == 200
    assert response.json() == {
        "recognized_text": RECOGNIZED,
        "translated_text": ENGLISH,
        "region_hint": REGION,
        "cached": False,
    }


def test_the_crop_and_the_language_reach_the_recognition_provider(
    client: TestClient,
) -> None:
    route_sarvam()
    route_translate()

    post(client)

    submitted = next(call for call in respx.calls if str(call.request.url) == PARSE_URL)
    body = submitted.request.content
    assert CROP in body, "the crop goes to the provider as it arrived"
    assert b"ml-IN" in body
    assert b'filename="frame.png"' in body


def test_the_recognized_text_is_what_is_translated(client: TestClient) -> None:
    """Every recognized block, in the language pair the app asked for.

    The translator is what normalises the spacing between the blocks, so that
    the same headline read twice is one cache entry; the answer still carries
    the text as it was recognized.
    """
    route_sarvam()
    translate = route_translate()

    post(client)

    sent = json.loads(translate.calls.last.request.content)
    assert sent["input"] == normalise(RECOGNIZED)
    assert sent["source_language_code"] == "ml-IN"
    assert sent["target_language_code"] == "en-IN"


def test_a_successful_frame_logs_the_two_provider_calls(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """The log lines the system test cases read — ST-5, ST-6, ST-8 — by name."""
    route_sarvam()
    route_translate()
    # The app was built before this test began, so its handler holds the
    # standard output of that moment; point the logger at this test's.
    configure_logging()

    post(client)

    written = lines(capsys.readouterr().out)
    recognition = next(line for line in written if line["event"] == "recognition.call")
    translation = next(line for line in written if line["event"] == "translation.call")
    assert recognition["provider"] == "sarvam-parse"
    assert translation["provider"] == "sarvam-translate"


def test_no_secret_reaches_the_answer_or_the_log(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    route_sarvam()
    route_translate()
    with TestClient(create_app(replace(settings, admin_token="admin-secret"))) as client:
        configure_logging()
        response = post(client)

    assert response.status_code == 200
    written = capsys.readouterr().out
    for secret in (settings.sarvam_api_key, "admin-secret"):
        assert secret
        assert secret not in response.text
        assert secret not in written


# --- The blank wall (ST-10) -------------------------------------------------


def test_a_frame_with_no_text_answers_with_nothing_and_translates_nothing(
    client: TestClient,
) -> None:
    route_sarvam(archive=parse_output([]))

    response = post(client)

    assert response.status_code == 200
    assert response.json() == {
        "recognized_text": "",
        "translated_text": "",
        "region_hint": None,
        "cached": False,
    }
    assert calls_to(TRANSLATE_URL) == 0, "nothing to translate, so no call"


def test_a_frame_whose_text_carries_no_box_has_no_region(client: TestClient) -> None:
    route_sarvam(archive=parse_output([{"text": HEADLINE, "tag": "header"}]))
    route_translate()

    answer = post(client).json()

    assert answer["recognized_text"] == HEADLINE
    assert answer["region_hint"] is None


# --- The cache (ST-5) -------------------------------------------------------


def test_the_same_headline_again_is_answered_from_the_cache(client: TestClient) -> None:
    route_sarvam()
    route_translate()

    first = post(client).json()
    second = post(client).json()

    assert first["cached"] is False
    assert second == {**first, "cached": True}
    assert calls_to(PARSE_URL) == 2, "every cycle is recognized afresh"
    assert calls_to(TRANSLATE_URL) == 1, "the second cycle is answered from the cache"


def test_a_new_headline_is_translated_again(client: TestClient) -> None:
    route_sarvam()
    route_translate()
    post(client)

    route_sarvam(archive=parse_output([{"text": OTHER_HEADLINE, "bbox": [0.1, 0.2, 0.5, 0.4]}]))
    route_translate(OTHER_ENGLISH)
    answer = post(client).json()

    assert answer["translated_text"] == OTHER_ENGLISH
    assert answer["cached"] is False
    assert calls_to(TRANSLATE_URL) == 2


# --- The 400 of the contract (ST-9) -----------------------------------------


@pytest.mark.parametrize(
    ("source_language", "target_language", "offending"),
    [
        ("fr-FR", "en-IN", "source language fr-FR is not configured"),
        ("ml-IN", "de-DE", "target language de-DE is not configured"),
    ],
)
def test_a_pair_the_configuration_does_not_offer_is_refused(
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
    source_language: str,
    target_language: str,
    offending: str,
) -> None:
    configure_logging()

    response = post(client, source_language=source_language, target_language=target_language)

    assert response.status_code == 400
    assert response.json() == {"error": {"code": "unsupported_language", "message": offending}}
    assert respx.calls.call_count == 0, "refused before any provider is involved"
    written = events(capsys.readouterr().out)
    assert "request.rejected" in written
    assert "recognition.call" not in written
    assert "translation.call" not in written


def test_a_configuration_that_cannot_be_read_is_an_invalid_configuration(
    client: TestClient, settings: Settings
) -> None:
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "languages.json").write_text("{not json", encoding="utf-8")

    response = post(client)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "invalid_configuration"
    assert "languages.json" not in response.text, "the caller is not told about our files"


# --- The 413 of the contract ------------------------------------------------


def test_an_image_past_the_cap_is_refused_before_any_provider_call(
    client: TestClient,
) -> None:
    response = post(client, image=padded(CROP, MAX_IMAGE_BYTES + 1))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "image_too_large"
    assert respx.calls.call_count == 0


# --- The 429 of the contract (ST-6) ----------------------------------------


def test_a_request_past_the_allowance_is_refused_with_a_retry_after(
    client: TestClient, settings: Settings
) -> None:
    route_sarvam()
    route_translate()
    budget_file(settings, recognition_per_minute=1, max_wait_seconds=0)

    assert post(client).status_code == 200
    refused = post(client)

    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "budget_exhausted"
    assert int(refused.headers["Retry-After"]) >= 1
    assert calls_to(PARSE_URL) == 1, "the allowance is never exceeded"


def test_the_deferred_request_is_logged_for_the_tester_to_read(
    client: TestClient, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    route_sarvam()
    route_translate()
    budget_file(settings, recognition_per_minute=1, max_wait_seconds=0)
    configure_logging()

    post(client)
    post(client)

    assert "recognition.deferred" in events(capsys.readouterr().out)


def test_a_deferred_frame_is_answered_once_the_allowance_comes_back(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half of the budget scenario: queued, not refused.

    `test_a_request_past_the_allowance_is_refused_with_a_retry_after` gives the
    request no time to wait (`max_wait_seconds=0`), so it proves the refusal.
    Here the second frame may wait, and does: it is deferred, the slot comes
    back when the oldest call leaves the minute, and the frame is then answered
    — the shape of ST-6, with the minute shortened to a twentieth of a second
    as `test_budget.py` shortens it.
    """
    route_sarvam()
    route_translate()
    budget_file(settings, recognition_per_minute=1, max_wait_seconds=30)
    app = create_app(settings)
    app.state.recognition_budget = recognition_budget(settings, window_seconds=0.05)

    with TestClient(app) as client:
        configure_logging()
        assert post(client).status_code == 200
        waited = post(client)

    assert waited.status_code == 200, "the second frame waited its turn, it was not refused"
    assert waited.json()["recognized_text"] == RECOGNIZED
    assert calls_to(PARSE_URL) == 2, "the deferred call went out after the slot came back"
    assert "recognition.deferred" in events(capsys.readouterr().out)


# --- The 504 and 502 of the contract ---------------------------------------


def test_a_job_that_never_finishes_is_a_recognition_timeout(
    client: TestClient, settings: Settings
) -> None:
    languages_file(settings, parse={"timeout_seconds": 0.05, "poll_interval_seconds": 0.01})
    route_sarvam(statuses=["pending"])

    response = post(client)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "recognition_timeout"
    assert calls_to(TRANSLATE_URL) == 0


def test_a_job_the_provider_gives_up_on_is_a_provider_error(client: TestClient) -> None:
    route_sarvam(statuses=["failed"])

    response = post(client)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"
    assert calls_to(TRANSLATE_URL) == 0


# --- The app token (D10) ----------------------------------------------------


def test_the_endpoint_is_open_when_no_app_token_is_set(client: TestClient) -> None:
    route_sarvam()
    route_translate()

    assert post(client).status_code == 200


def test_a_call_without_the_app_token_is_refused_once_one_is_set(
    settings: Settings,
) -> None:
    with TestClient(create_app(replace(settings, app_token=APP_TOKEN))) as client:
        refused = post(client)

    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "unauthorized"
    assert respx.calls.call_count == 0, "refused before any provider is involved"


def test_a_call_carrying_the_app_token_is_answered(settings: Settings) -> None:
    route_sarvam()
    route_translate()

    with TestClient(create_app(replace(settings, app_token=APP_TOKEN))) as client:
        allowed = post(client, headers={"Authorization": f"Bearer {APP_TOKEN}"})

    assert allowed.status_code == 200
    assert allowed.json()["translated_text"] == ENGLISH
