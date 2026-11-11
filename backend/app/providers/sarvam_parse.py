"""Sarvam document recognition: what the text in a cropped frame says, and where.

The flow is Sarvam's three calls (verified against docs.sarvam.ai, and quoted
in the design's "Contract with Sarvam"):

1. `POST /doc-ai/v1/job/parse` — the crop as a multipart file, the configured
   source language, `output_format=json`. Answers with a job id.
2. `GET /doc-ai/v1/job/<id>/status` — polled once a second until the job
   reaches a terminal state.
3. `GET /doc-ai/v1/job/<id>/download-url` — a pre-signed link to a ZIP whose
   primary JSON file holds the recognized text blocks with their bounding
   boxes. The link needs no credential, so this client sends none with it.

The whole sequence is held to one deadline (12 seconds by default): past it the
caller gets `recognition_timeout`, and a job Sarvam failed or rejected becomes
`provider_error`. The API key is read from `app.settings` — that is, from the
environment — and goes nowhere but the request header: it is in no log line, no
error message and no response body.

**Bounding box shapes.** Sarvam documents that each JSON block carries text, a
tag and a bounding box, but not the field names or the coordinate space. This
module therefore reads the block tree tolerantly: it takes text from the
outermost `text`/`content`/`value` of each block, and a box from any of the
usual spellings (`bbox`, `bounding_box`, corner pairs, an x/y/width/height
object, or a polygon's points). Boxes are taken as pixels of the uploaded
image, which for an image upload is the page, and normalised 0-1 against that
image's own size; a box already inside 0-1 is left as it is. The latency and
fidelity spike the proposal calls for is what will confirm the real shape.
"""

from __future__ import annotations

import asyncio
import io
import json
import time
import zipfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from ..errors import ApiError
from ..images import image_dimensions
from ..logging_setup import log_event
from ..settings import Settings

PROVIDER_KIND = "sarvam_parse"
BASE_URL = "https://api.sarvam.ai"
API_KEY_HEADER = "api-subscription-key"
OUTPUT_FORMAT = "json"

DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_POLL_INTERVAL_SECONDS = 1.0

SUCCESS_STATUSES = frozenset({"completed", "partially_completed"})
FAILURE_STATUSES = frozenset({"failed", "rejected"})

# What a provider body may contribute to a log line, so a huge page of HTML
# cannot turn one event into a screenful.
_BODY_SNIPPET = 300


@dataclass(frozen=True)
class Region:
    """A rectangle in the uploaded image, as fractions of its width and height."""

    x: float
    y: float
    width: float
    height: float

    def as_dict(self) -> dict[str, float]:
        """The `region_hint` object of the API contract."""
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class TextBlock:
    """One recognized block: what it says, and the box it sits in."""

    text: str
    box: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class Recognition:
    """Everything recognition knows about one frame."""

    text: str
    region_hint: Region | None
    blocks: tuple[TextBlock, ...]
    job_id: str


class SarvamParseClient:
    """Recognition through Sarvam's document parse jobs.

    One client per provider entry in the languages configuration; the entry's
    name is what every `recognition.call` line is logged against, because that
    name is what a reader of the log compares with the configuration.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        provider_name: str = "sarvam-parse",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        base_url: str = BASE_URL,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.settings = settings
        self.provider_name = provider_name
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.base_url = base_url.rstrip("/")
        self._client_factory = client_factory or httpx.AsyncClient
        self._monotonic = monotonic
        self._sleep = sleep or asyncio.sleep

    @classmethod
    def from_provider_entry(
        cls,
        name: str,
        entry: Mapping[str, Any],
        settings: Settings,
        **overrides: Any,
    ) -> SarvamParseClient:
        """Build the client the configuration's provider entry `name` describes.

        The entry's `kind` has to be `sarvam_parse`; a wrong kind is an
        operator's configuration mistake, so it is named plainly. `timeout_seconds`
        and `poll_interval_seconds` are optional in the entry, which is what makes
        the design's 12 seconds and 1 second configurable without a restart. Every
        value an operator may have mistyped is checked here, where the answer is
        still a plain refusal naming the key, rather than at request time.
        """
        kind = entry.get("kind")
        if kind != PROVIDER_KIND:
            raise ApiError(
                502,
                "provider_error",
                f"Recognition provider {name} is configured as {kind!r}, "
                f"but this client only speaks {PROVIDER_KIND!r}.",
                log_fields={"provider": name, "provider_kind": kind},
            )
        from_entry: dict[str, Any] = {
            key: _seconds(name, key, entry[key])
            for key in ("timeout_seconds", "poll_interval_seconds")
            if key in entry
        }
        return cls(settings, provider_name=name, **{**from_entry, **overrides})

    async def recognize(
        self,
        image: bytes,
        *,
        language: str,
        filename: str = "frame.jpg",
        content_type: str = "image/jpeg",
    ) -> Recognition:
        """Recognize the text in one cropped frame.

        Raises `ApiError` with `recognition_timeout` (504) when the job does not
        finish inside the deadline, and with `provider_error` (502) when Sarvam
        fails, is unreachable, or answers something this client cannot read. An
        image with no text in it is not a failure: the text comes back empty and
        the region hint is None (the blank wall of the contract).
        """
        api_key = self.settings.sarvam_api_key
        if not api_key:
            raise self._provider_error(
                "The recognition provider is not configured: SARVAM_API_KEY is "
                "not set in the backend's environment.",
                reason="missing_api_key",
            )

        deadline = self._monotonic() + self.timeout_seconds
        headers = {API_KEY_HEADER: api_key}

        async with self._client_factory() as client:
            job_id = await self._submit(
                client,
                headers,
                deadline,
                image=image,
                language=language,
                filename=filename,
                content_type=content_type,
            )
            log_event("recognition.call", provider=self.provider_name, job_id=job_id)
            await self._await_terminal(client, headers, deadline, job_id)
            archive = await self._download(client, headers, deadline, job_id)

        blocks = read_blocks(archive, job_id=job_id, provider=self.provider_name)
        return Recognition(
            text="\n".join(block.text for block in blocks),
            region_hint=region_hint(blocks, image),
            blocks=blocks,
            job_id=job_id,
        )

    async def _submit(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        deadline: float,
        *,
        image: bytes,
        language: str,
        filename: str,
        content_type: str,
    ) -> str:
        response = await self._request(
            client,
            "POST",
            f"{self.base_url}/doc-ai/v1/job/parse",
            headers,
            deadline,
            files={"file": (filename, image, content_type)},
            data={"language": language, "output_format": OUTPUT_FORMAT},
        )
        job_id = _string_field(self._json_body(response), "job_id")
        if not job_id:
            raise self._provider_error(
                "The recognition provider accepted the image without returning a job.",
                reason="no_job_id",
            )
        return job_id

    async def _await_terminal(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        deadline: float,
        job_id: str,
    ) -> str:
        """Poll until the job is terminal; a success status is the only way out."""
        while True:
            response = await self._request(
                client,
                "GET",
                f"{self.base_url}/doc-ai/v1/job/{job_id}/status",
                headers,
                deadline,
                job_id=job_id,
            )
            reported = _string_field(self._json_body(response), "status")
            status = (reported or "").lower()
            if status in SUCCESS_STATUSES:
                return status
            if status in FAILURE_STATUSES:
                raise self._provider_error(
                    f"The recognition provider {status} this image.",
                    job_id=job_id,
                    sarvam_status=status,
                    reason="terminal_failure",
                )
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise self._timeout_error(job_id=job_id, sarvam_status=status or None)
            await self._sleep(min(self.poll_interval_seconds, remaining))

    async def _download(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        deadline: float,
        job_id: str,
    ) -> bytes:
        response = await self._request(
            client,
            "GET",
            f"{self.base_url}/doc-ai/v1/job/{job_id}/download-url",
            headers,
            deadline,
            job_id=job_id,
        )
        url = _string_field(self._json_body(response), "url")
        if not url:
            raise self._provider_error(
                "The recognition provider finished the job without a download link.",
                job_id=job_id,
                reason="no_download_url",
            )
        # The link is pre-signed: it carries its own authorisation, so the API
        # key stays out of this request entirely.
        archive = await self._request(client, "GET", url, {}, deadline, job_id=job_id)
        return archive.content

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str],
        deadline: float,
        *,
        job_id: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """One call to the provider, inside what is left of the deadline."""
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise self._timeout_error(job_id=job_id)
        try:
            response = await client.request(
                method, url, headers=headers, timeout=remaining, **kwargs
            )
        except httpx.TimeoutException as exc:
            raise self._timeout_error(job_id=job_id) from exc
        except httpx.HTTPError as exc:
            raise self._provider_error(
                "The recognition provider could not be reached.",
                job_id=job_id,
                reason=type(exc).__name__,
            ) from exc
        if response.status_code >= 400:
            raise self._provider_error(
                f"The recognition provider answered with HTTP {response.status_code}.",
                job_id=job_id,
                provider_status=response.status_code,
                provider_body=response.text[:_BODY_SNIPPET],
                reason="http_error",
            )
        return response

    def _json_body(self, response: httpx.Response) -> Mapping[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise self._provider_error(
                "The recognition provider answered with something that is not JSON.",
                reason="unreadable_body",
            ) from exc
        if not isinstance(body, Mapping):
            raise self._provider_error(
                "The recognition provider answered with something that is not JSON.",
                reason="unreadable_body",
            )
        return body

    def _provider_error(self, message: str, **log_fields: Any) -> ApiError:
        return ApiError(
            502,
            "provider_error",
            message,
            log_fields={"provider": self.provider_name, **_present(log_fields)},
        )

    def _timeout_error(self, **log_fields: Any) -> ApiError:
        return ApiError(
            504,
            "recognition_timeout",
            "The recognition provider did not finish reading this image in time.",
            log_fields={
                "provider": self.provider_name,
                "timeout_seconds": self.timeout_seconds,
                **_present(log_fields),
            },
        )


def _seconds(provider: str, key: str, value: Any) -> float:
    """A number of seconds an operator wrote in configuration, or a refusal.

    JSON keeps `12` and `"12"` apart, so a string here is a typo in the file
    rather than a value to rescue: saying which key is wrong is more use to the
    operator than quietly accepting it.
    """
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ApiError(
            502,
            "provider_error",
            f"Recognition provider {provider} has {key} set to {value!r}, "
            "which is not a number of seconds above zero.",
            log_fields={"provider": provider, "setting": key},
        )
    return float(value)


def _present(fields: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}


def _string_field(body: Mapping[str, Any], name: str) -> str | None:
    value = body.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


# --- Reading the ZIP -------------------------------------------------------

_TEXT_KEYS = ("text", "content", "value")
_BOX_KEYS = (
    "bbox",
    "bounding_box",
    "boundingBox",
    "box",
    "bounds",
    "rect",
    "polygon",
    "points",
    "vertices",
    "coordinates",
)
_CORNER_KEY_SETS = (
    ("x0", "y0", "x1", "y1"),
    ("xmin", "ymin", "xmax", "ymax"),
    ("x_min", "y_min", "x_max", "y_max"),
    ("left", "top", "right", "bottom"),
    ("l", "t", "r", "b"),
)
_SIZE_KEY_SETS = (
    ("x", "y", "width", "height"),
    ("x", "y", "w", "h"),
    ("left", "top", "width", "height"),
)


def read_blocks(archive: bytes, *, job_id: str, provider: str) -> tuple[TextBlock, ...]:
    """The text blocks of a parse job's output ZIP, in the order it lists them."""
    payload = _primary_json(archive, job_id=job_id, provider=provider)
    blocks: list[TextBlock] = []
    _collect(payload, blocks)
    return tuple(blocks)


def _primary_json(archive: bytes, *, job_id: str, provider: str) -> Any:
    """The job's own output file — not `manifest.json`, not the page metadata."""

    def failure(message: str, reason: str) -> ApiError:
        return ApiError(
            502,
            "provider_error",
            message,
            log_fields={"provider": provider, "job_id": job_id, "reason": reason},
        )

    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            names = [
                name
                for name in bundle.namelist()
                if name.endswith(".json")
                and "metadata/" not in name
                and not name.endswith("manifest.json")
            ]
            if not names:
                raise failure(
                    "The recognition provider's output held no recognized text.",
                    "no_output_file",
                )
            raw = bundle.read(names[0])
    except zipfile.BadZipFile as exc:
        raise failure(
            "The recognition provider's output could not be opened.", "bad_archive"
        ) from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise failure(
            "The recognition provider's output could not be read.", "unreadable_output"
        ) from exc


def _collect(node: Any, out: list[TextBlock]) -> None:
    """Walk the block tree, taking the outermost text-bearing level of it.

    A block that has text of its own is taken whole and not descended into, so
    a page's lines and words are not counted again underneath it. The exception
    is a block with text but no box whose children do carry boxes — there the
    detail is worth more than the summary, because the boxes are the region
    hint.
    """
    if isinstance(node, Mapping):
        text = _text_of(node)
        box = _box_of(node)
        if text and (box is not None or not _has_boxed_child(node)):
            out.append(TextBlock(text=text, box=box))
            return
        for key, value in node.items():
            if key not in _BOX_KEYS:
                _collect(value, out)
        return
    if isinstance(node, Sequence) and not isinstance(node, str | bytes):
        for item in node:
            _collect(item, out)


def _has_boxed_child(node: Mapping[str, Any]) -> bool:
    for key, value in node.items():
        if key in _BOX_KEYS:
            continue
        if _carries_box(value):
            return True
    return False


def _carries_box(node: Any) -> bool:
    if isinstance(node, Mapping):
        if _box_of(node) is not None:
            return True
        return any(_carries_box(value) for key, value in node.items() if key not in _BOX_KEYS)
    if isinstance(node, Sequence) and not isinstance(node, str | bytes):
        return any(_carries_box(item) for item in node)
    return False


def _text_of(node: Mapping[str, Any]) -> str:
    for key in _TEXT_KEYS:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _box_of(node: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    for key in _BOX_KEYS:
        if key in node:
            box = _parse_box(node[key])
            if box is not None:
                return box
    return _box_from_keys(node)


def _parse_box(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, Mapping):
        return _box_of(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        numbers = [_number(item) for item in value]
        if len(numbers) == 4 and all(number is not None for number in numbers):
            first, second, third, fourth = (float(number) for number in numbers)  # type: ignore[arg-type]
            # Four numbers are corners unless the far corner sits before the
            # near one, which only makes sense as a width and a height.
            if third < first or fourth < second:
                return _ordered(first, second, first + third, second + fourth)
            return _ordered(first, second, third, fourth)
        return _box_from_points(value)
    return None


def _box_from_points(value: Sequence[Any]) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for point in value:
        pair = _point(point)
        if pair is None:
            return None
        xs.append(pair[0])
        ys.append(pair[1])
    if len(xs) < 2:
        return None
    return _ordered(min(xs), min(ys), max(xs), max(ys))


def _point(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        x, y = _number(value.get("x")), _number(value.get("y"))
        if x is not None and y is not None:
            return float(x), float(y)
        return None
    if isinstance(value, Sequence) and not isinstance(value, str | bytes) and len(value) == 2:
        x, y = _number(value[0]), _number(value[1])
        if x is not None and y is not None:
            return float(x), float(y)
    return None


def _box_from_keys(node: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    for keys in _CORNER_KEY_SETS:
        values = [_number(node.get(key)) for key in keys]
        if all(value is not None for value in values):
            x0, y0, x1, y1 = (float(value) for value in values)  # type: ignore[arg-type]
            return _ordered(x0, y0, x1, y1)
    for keys in _SIZE_KEY_SETS:
        values = [_number(node.get(key)) for key in keys]
        if all(value is not None for value in values):
            x, y, width, height = (float(value) for value in values)  # type: ignore[arg-type]
            return _ordered(x, y, x + width, y + height)
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _ordered(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


# --- The region hint -------------------------------------------------------


def region_hint(blocks: Sequence[TextBlock], image: bytes) -> Region | None:
    """The union of the blocks' boxes, as fractions of the uploaded image.

    Sarvam does not document whether its coordinates are pixels or fractions,
    so the numbers decide, and they decide before the image is measured: a box
    whose every coordinate already sits inside 0-1 is taken as fractions and
    used as it is. Read as pixels the same box could only describe text inside
    the image's top-left single pixel, which is never what a reader is looking
    at, so there is nothing to lose by reading it the other way — and dividing
    it by the pixel size would put the overlay in that corner, tiny.

    None when nothing was recognized, when no block carried a box, or when the
    boxes are pixels of an image this backend cannot measure — the contract
    would rather say nothing than anchor the overlay wrongly.
    """
    boxes = [block.box for block in blocks if block.box is not None]
    if not boxes:
        return None
    x0 = min(box[0] for box in boxes)
    y0 = min(box[1] for box in boxes)
    x1 = max(box[2] for box in boxes)
    y1 = max(box[3] for box in boxes)

    if min(x0, y0) >= 0.0 and max(x1, y1) <= 1.0:
        return _region(x0, y0, x1, y1)
    size = image_dimensions(image)
    if size is None:
        return None
    width, height = size
    return _region(x0 / width, y0 / height, x1 / width, y1 / height)


def _region(x0: float, y0: float, x1: float, y1: float) -> Region:
    left = _clamped(x0)
    top = _clamped(y0)
    return Region(
        x=round(left, 4),
        y=round(top, 4),
        width=round(_clamped(x1) - left, 4),
        height=round(_clamped(y1) - top, 4),
    )


def _clamped(value: float) -> float:
    return min(1.0, max(0.0, value))
