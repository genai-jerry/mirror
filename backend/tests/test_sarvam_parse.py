"""The Sarvam recognition client, with Sarvam faked by respx.

Not one test here reaches the real provider: every route is declared, so an
undeclared call fails the test rather than leaving the factory's runner to call
Sarvam for real (`qa_notes`).
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx

from app.errors import ApiError
from app.logging_setup import configure_logging, set_request_id
from app.providers.sarvam_parse import (
    API_KEY_HEADER,
    DEFAULT_TIMEOUT_SECONDS,
    SarvamParseClient,
    TextBlock,
    read_blocks,
    region_hint,
)
from app.settings import Settings
from tests.test_images import jpeg, png

PARSE_URL = "https://api.sarvam.ai/doc-ai/v1/job/parse"
JOB = "019fb81e-2543-70bd-a737-b5a2d62a3bb7"
STATUS_URL = f"https://api.sarvam.ai/doc-ai/v1/job/{JOB}/status"
DOWNLOAD_URL_URL = f"https://api.sarvam.ai/doc-ai/v1/job/{JOB}/download-url"
ARCHIVE_URL = "https://sarvam-outputs.example.com/signed/output.zip"

HEADLINE = "കേരളത്തിൽ മഴ തുടരുന്നു"
SUBHEAD = "വിവിധ ജില്ലകളിൽ ജാഗ്രതാ നിർദേശം"


class Clock:
    """A monotonic clock that only moves when the client sleeps."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def parse_output(blocks: list[dict[str, Any]], *, upload: str = "frame.jpg") -> bytes:
    """A parse job's output ZIP: manifest, primary JSON, per-page metadata."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps({"job_id": JOB, "pipeline": "parse"}))
        bundle.writestr(f"{upload}/metadata/page_001.json", json.dumps({"page": 1}))
        bundle.writestr(f"{upload}/{upload}.json", json.dumps({"blocks": blocks}))
    return buffer.getvalue()


HEADLINE_BLOCKS = [
    {"text": HEADLINE, "tag": "header", "bbox": [80, 205, 920, 290]},
    {"text": SUBHEAD, "tag": "paragraph", "bbox": [120, 300, 880, 340]},
]


def route_sarvam(
    *,
    statuses: list[str] | None = None,
    archive: bytes | None = None,
) -> None:
    """Declare the three Sarvam calls plus the pre-signed download."""
    respx.post(PARSE_URL).mock(
        return_value=httpx.Response(200, json={"job_id": JOB, "status": "pending"})
    )
    bodies = [
        httpx.Response(200, json={"job_id": JOB, "status": status})
        for status in (statuses or ["completed"])
    ]
    status_route = respx.get(STATUS_URL)
    if len(bodies) == 1:
        status_route.mock(return_value=bodies[0])
    else:
        status_route.mock(side_effect=bodies)
    respx.get(DOWNLOAD_URL_URL).mock(
        return_value=httpx.Response(200, json={"method": "GET", "url": ARCHIVE_URL})
    )
    respx.get(ARCHIVE_URL).mock(
        return_value=httpx.Response(
            200,
            content=parse_output(HEADLINE_BLOCKS) if archive is None else archive,
        )
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def recognizer(settings: Settings, clock: Clock) -> SarvamParseClient:
    return SarvamParseClient(settings, monotonic=clock, sleep=clock.sleep)


@pytest.fixture(autouse=True)
def sarvam() -> Iterator[respx.MockRouter]:
    """Sarvam is mocked for every test in this file; an undeclared call fails."""
    with respx.mock:
        yield respx.mock


def lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.strip().splitlines() if line.strip()]


# --- The happy path --------------------------------------------------------


async def test_a_headline_comes_back_with_its_region(recognizer: SarvamParseClient) -> None:
    """The region hint is the union of the text blocks, as fractions of the crop."""
    route_sarvam()

    recognized = await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert recognized.text == f"{HEADLINE}\n{SUBHEAD}"
    assert recognized.job_id == JOB
    assert recognized.region_hint is not None
    assert recognized.region_hint.as_dict() == {
        "x": 0.08,
        "y": 0.41,
        "width": 0.84,
        "height": 0.27,
    }


async def test_the_job_is_submitted_with_the_crop_and_the_language(
    recognizer: SarvamParseClient,
) -> None:
    route_sarvam()
    image = jpeg(640, 480)

    await recognizer.recognize(image, language="ml-IN", filename="crop.jpg")

    request = respx.calls[0].request
    assert request.url == PARSE_URL
    assert request.headers[API_KEY_HEADER] == "test-key"
    body = request.content
    assert b'name="language"' in body and b"ml-IN" in body
    assert b'name="output_format"' in body and b"json" in body
    assert b"crop.jpg" in body
    assert image in body, "the crop itself is what gets recognized"


async def test_the_api_key_never_reaches_the_download_link(
    recognizer: SarvamParseClient,
) -> None:
    """The link is pre-signed, so sending the key with it would only risk it."""
    route_sarvam()

    await recognizer.recognize(png(1000, 500), language="ml-IN")

    download = next(call for call in respx.calls if str(call.request.url) == ARCHIVE_URL)
    assert API_KEY_HEADER not in download.request.headers
    assert "test-key" not in str(download.request.headers)


async def test_a_pending_job_is_polled_until_it_finishes(
    recognizer: SarvamParseClient, clock: Clock
) -> None:
    route_sarvam(statuses=["pending", "running", "running", "completed"])

    recognized = await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert recognized.text.startswith(HEADLINE)
    polls = [call for call in respx.calls if str(call.request.url) == STATUS_URL]
    assert len(polls) == 4
    assert clock.now == 3.0, "one second between polls (the design's cadence)"


async def test_a_partly_finished_job_is_still_read(recognizer: SarvamParseClient) -> None:
    """Sarvam's `partially_completed` has output; a headline needs one page."""
    route_sarvam(statuses=["partially_completed"])

    recognized = await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert recognized.text.startswith(HEADLINE)


async def test_a_blank_wall_recognizes_nothing_and_fails_nothing(
    recognizer: SarvamParseClient,
) -> None:
    route_sarvam(archive=parse_output([]))

    recognized = await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert recognized.text == ""
    assert recognized.region_hint is None
    assert recognized.blocks == ()


async def test_the_recognition_call_is_logged_with_its_provider_and_job(
    recognizer: SarvamParseClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """The design's logged-events table is what ST-5, ST-6 and ST-8 read."""
    route_sarvam()
    configure_logging()
    set_request_id("req-1")
    capsys.readouterr()

    await recognizer.recognize(png(1000, 500), language="ml-IN")

    (line,) = lines(capsys.readouterr().out)
    assert line["event"] == "recognition.call"
    assert line["provider"] == "sarvam-parse"
    assert line["job_id"] == JOB
    assert line["request_id"] == "req-1"


async def test_the_key_appears_in_no_log_line(
    recognizer: SarvamParseClient, capsys: pytest.CaptureFixture[str]
) -> None:
    route_sarvam()
    configure_logging()
    capsys.readouterr()

    await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert "test-key" not in capsys.readouterr().out


# --- When it goes wrong ----------------------------------------------------


@pytest.mark.parametrize("status", ["failed", "rejected"])
async def test_a_job_sarvam_gives_up_on_is_a_provider_error(
    recognizer: SarvamParseClient, status: str
) -> None:
    route_sarvam(statuses=[status])

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert (raised.value.status_code, raised.value.code) == (502, "provider_error")
    assert raised.value.log_fields["sarvam_status"] == status
    assert raised.value.log_fields["job_id"] == JOB


async def test_a_job_that_never_finishes_times_out(
    recognizer: SarvamParseClient, clock: Clock
) -> None:
    """The deadline covers the whole sequence, not one call of it (design D-level 12s)."""
    route_sarvam(statuses=["running"])

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert (raised.value.status_code, raised.value.code) == (504, "recognition_timeout")
    assert clock.now == DEFAULT_TIMEOUT_SECONDS
    assert raised.value.log_fields["timeout_seconds"] == DEFAULT_TIMEOUT_SECONDS


async def test_a_slow_provider_call_is_a_recognition_timeout(
    recognizer: SarvamParseClient,
) -> None:
    respx.post(PARSE_URL).mock(side_effect=httpx.ReadTimeout("too slow"))

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert (raised.value.status_code, raised.value.code) == (504, "recognition_timeout")


async def test_an_unreachable_provider_is_a_provider_error(
    recognizer: SarvamParseClient,
) -> None:
    respx.post(PARSE_URL).mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert (raised.value.status_code, raised.value.code) == (502, "provider_error")


async def test_a_refused_submission_is_a_provider_error(
    recognizer: SarvamParseClient,
) -> None:
    respx.post(PARSE_URL).mock(return_value=httpx.Response(429, json={"error": "slow down"}))

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert (raised.value.status_code, raised.value.code) == (502, "provider_error")
    assert raised.value.log_fields["provider_status"] == 429
    assert "429" in raised.value.message


async def test_a_submission_with_no_job_is_a_provider_error(
    recognizer: SarvamParseClient,
) -> None:
    respx.post(PARSE_URL).mock(return_value=httpx.Response(200, json={"status": "pending"}))

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert raised.value.log_fields["reason"] == "no_job_id"


async def test_an_answer_that_is_not_json_is_a_provider_error(
    recognizer: SarvamParseClient,
) -> None:
    respx.post(PARSE_URL).mock(return_value=httpx.Response(200, text="<html>maintenance</html>"))

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert raised.value.log_fields["reason"] == "unreadable_body"


async def test_a_finished_job_with_no_download_link_is_a_provider_error(
    recognizer: SarvamParseClient,
) -> None:
    route_sarvam()
    respx.get(DOWNLOAD_URL_URL).mock(return_value=httpx.Response(200, json={"method": "GET"}))

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert raised.value.log_fields["reason"] == "no_download_url"


async def test_output_that_is_not_a_zip_is_a_provider_error(
    recognizer: SarvamParseClient,
) -> None:
    route_sarvam(archive=b"not a zip at all")

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert raised.value.log_fields["reason"] == "bad_archive"


async def test_output_with_no_primary_file_is_a_provider_error(
    recognizer: SarvamParseClient,
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("manifest.json", "{}")
        bundle.writestr("frame.jpg/metadata/page_001.json", "{}")
    route_sarvam(archive=buffer.getvalue())

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert raised.value.log_fields["reason"] == "no_output_file"


async def test_output_that_is_not_json_is_a_provider_error(
    recognizer: SarvamParseClient,
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("frame.jpg/frame.jpg.json", "{not json")
    route_sarvam(archive=buffer.getvalue())

    with pytest.raises(ApiError) as raised:
        await recognizer.recognize(png(1000, 500), language="ml-IN")

    assert raised.value.log_fields["reason"] == "unreadable_output"


async def test_a_missing_key_is_refused_before_any_call(
    settings: Settings, clock: Clock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without SARVAM_API_KEY every recognition fails — and says which name is missing."""
    route_sarvam()
    keyless = SarvamParseClient(
        Settings(
            sarvam_api_key=None,
            admin_token=None,
            app_token=None,
            config_dir=settings.config_dir,
            defaults_dir=settings.defaults_dir,
        ),
        monotonic=clock,
        sleep=clock.sleep,
    )
    configure_logging()
    capsys.readouterr()

    with pytest.raises(ApiError) as raised:
        await keyless.recognize(png(1000, 500), language="ml-IN")

    assert (raised.value.status_code, raised.value.code) == (502, "provider_error")
    assert "SARVAM_API_KEY" in raised.value.message
    assert not respx.calls, "a request with no key must not be sent"


# --- Provider entries ------------------------------------------------------


def test_a_provider_entry_names_the_client_and_may_retune_it(settings: Settings) -> None:
    entry = {"kind": "sarvam_parse", "timeout_seconds": 4, "poll_interval_seconds": 0.5}

    client = SarvamParseClient.from_provider_entry("sarvam-parse-fast", entry, settings)

    assert client.provider_name == "sarvam-parse-fast"
    assert client.timeout_seconds == 4
    assert client.poll_interval_seconds == 0.5


def test_a_provider_entry_keeps_the_designed_defaults(settings: Settings) -> None:
    client = SarvamParseClient.from_provider_entry(
        "sarvam-parse", {"kind": "sarvam_parse"}, settings
    )

    assert client.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert client.poll_interval_seconds == 1.0


def test_a_provider_entry_of_another_kind_is_refused(settings: Settings) -> None:
    """An operator who points recognition at the translation provider is told so."""
    with pytest.raises(ApiError) as raised:
        SarvamParseClient.from_provider_entry(
            "sarvam-translate", {"kind": "sarvam_translate"}, settings
        )

    assert raised.value.code == "provider_error"
    assert "sarvam-translate" in raised.value.message


# --- Reading the blocks ----------------------------------------------------


def blocks_of(payload: Any) -> tuple[TextBlock, ...]:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("frame.jpg/frame.jpg.json", json.dumps(payload))
    return read_blocks(buffer.getvalue(), job_id=JOB, provider="sarvam-parse")


@pytest.mark.parametrize(
    "box",
    [
        pytest.param([10, 20, 110, 220], id="corner list"),
        pytest.param({"x0": 10, "y0": 20, "x1": 110, "y1": 220}, id="corner keys"),
        pytest.param({"xmin": 10, "ymin": 20, "xmax": 110, "ymax": 220}, id="min and max"),
        pytest.param({"left": 10, "top": 20, "right": 110, "bottom": 220}, id="edges"),
        pytest.param({"x": 10, "y": 20, "width": 100, "height": 200}, id="size keys"),
        pytest.param({"x": 10, "y": 20, "w": 100, "h": 200}, id="short size keys"),
        pytest.param(
            [{"x": 10, "y": 20}, {"x": 110, "y": 20}, {"x": 110, "y": 220}, {"x": 10, "y": 220}],
            id="polygon of points",
        ),
        pytest.param([[10, 20], [110, 220]], id="polygon of pairs"),
    ],
)
def test_a_box_is_read_however_sarvam_spells_it(box: Any) -> None:
    """The field names are undocumented, so every plausible spelling is read."""
    (block,) = blocks_of({"blocks": [{"text": HEADLINE, "bbox": box}]})

    assert block.box == (10.0, 20.0, 110.0, 220.0)


def test_four_numbers_that_cannot_be_corners_are_a_size() -> None:
    """A far corner before the near one only makes sense as a width and a height."""
    (block,) = blocks_of({"blocks": [{"text": HEADLINE, "bbox": [10, 20, 100, 7]}]})

    assert block.box == (10.0, 20.0, 110.0, 27.0)


def test_a_box_beside_the_text_is_read() -> None:
    """Some shapes hang the coordinates off the block itself, with no box key."""
    (block,) = blocks_of([{"text": HEADLINE, "x": 10, "y": 20, "width": 100, "height": 200}])

    assert block.box == (10.0, 20.0, 110.0, 220.0)


def test_blocks_keep_the_order_the_provider_listed_them_in() -> None:
    blocks = blocks_of({"pages": [{"blocks": HEADLINE_BLOCKS}]})

    assert [block.text for block in blocks] == [HEADLINE, SUBHEAD]


def test_a_block_is_not_counted_again_under_itself() -> None:
    """A page that repeats its lines inside its blocks must not double the text."""
    payload = {
        "blocks": [
            {
                "text": HEADLINE,
                "bbox": [80, 205, 920, 290],
                "lines": [{"text": HEADLINE, "bbox": [80, 205, 920, 290]}],
            }
        ]
    }

    assert [block.text for block in blocks_of(payload)] == [HEADLINE]


def test_the_detailed_lines_win_over_a_summary_with_no_box() -> None:
    """A whole-page string with no box of its own would leave nothing to anchor to."""
    payload = {
        "text": f"{HEADLINE} {SUBHEAD}",
        "blocks": [
            {"text": HEADLINE, "bbox": [80, 205, 920, 290]},
            {"text": SUBHEAD, "bbox": [120, 300, 880, 340]},
        ],
    }

    assert [block.text for block in blocks_of(payload)] == [HEADLINE, SUBHEAD]


def test_a_block_with_no_box_still_keeps_its_text() -> None:
    (block,) = blocks_of({"blocks": [{"text": HEADLINE}]})

    assert (block.text, block.box) == (HEADLINE, None)


def test_text_may_be_called_content_or_value() -> None:
    blocks = blocks_of({"blocks": [{"content": HEADLINE}, {"value": SUBHEAD}]})

    assert [block.text for block in blocks] == [HEADLINE, SUBHEAD]


# --- The region hint -------------------------------------------------------


def test_the_region_is_the_union_of_the_boxes() -> None:
    blocks = [
        TextBlock(text=HEADLINE, box=(80, 205, 920, 290)),
        TextBlock(text=SUBHEAD, box=(120, 300, 880, 340)),
    ]

    hint = region_hint(blocks, png(1000, 500))

    assert hint is not None
    assert hint.as_dict() == {"x": 0.08, "y": 0.41, "width": 0.84, "height": 0.27}


def test_a_region_never_leaves_the_image() -> None:
    """A box the provider reports past the edge is clamped, not passed on."""
    hint = region_hint([TextBlock(text=HEADLINE, box=(-50, -10, 1200, 600))], png(1000, 500))

    assert hint is not None
    assert hint.as_dict() == {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}


def test_no_box_means_no_region() -> None:
    assert region_hint([TextBlock(text=HEADLINE, box=None)], png(1000, 500)) is None


def test_no_text_means_no_region() -> None:
    assert region_hint([], png(1000, 500)) is None


def test_boxes_that_are_already_fractions_are_left_alone() -> None:
    """An image this backend cannot measure, with a box that is plainly 0-1."""
    hint = region_hint([TextBlock(text=HEADLINE, box=(0.1, 0.2, 0.5, 0.6))], b"GIF89a")

    assert hint is not None
    assert hint.as_dict() == {"x": 0.1, "y": 0.2, "width": 0.4, "height": 0.4}


def test_pixels_against_an_unmeasurable_image_give_no_region() -> None:
    """Rather than anchor the overlay to a guess, the hint is left out."""
    assert region_hint([TextBlock(text=HEADLINE, box=(80, 205, 920, 290))], b"GIF89a") is None
