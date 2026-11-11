"""Reading the frame out of a multipart form: what is accepted, and what is not.

These tests drive `read_frame_upload` through an application of their own, so
what they prove is about the upload and not about the pipeline behind it —
`tests/test_frames.py` covers that.
"""

from __future__ import annotations

from collections.abc import Iterator
from tempfile import SpooledTemporaryFile
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.errors import ApiError, api_error_handler
from app.uploads import MAX_IMAGE_BYTES, read_frame_upload
from tests.test_images import jpeg, png

PATH = "/upload"


def padded(image: bytes, total: int) -> bytes:
    """An image of `total` bytes: a real header with filler behind it."""
    return image + b"\x00" * (total - len(image))


def form(
    image: bytes | None = None,
    *,
    filename: str = "crop.jpg",
    media_type: str = "image/jpeg",
    source_language: str | None = "ml-IN",
    target_language: str | None = "en-IN",
) -> dict[str, Any]:
    """The keyword arguments that post one frame, with any part left out."""
    fields = {
        "source_language": source_language,
        "target_language": target_language,
    }
    posted: dict[str, Any] = {
        "data": {name: value for name, value in fields.items() if value is not None}
    }
    if image is not None:
        posted["files"] = {"image": (filename, image, media_type)}
    return posted


@pytest.fixture
def uploads_client() -> Iterator[TestClient]:
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)

    @app.post(PATH)
    async def upload(request: Request) -> dict[str, Any]:
        frame = await read_frame_upload(request)
        return {
            "bytes": len(frame.image),
            "filename": frame.filename,
            "media_type": frame.media_type,
            "source_language": frame.source_language,
            "target_language": frame.target_language,
        }

    with TestClient(app) as client:
        yield client


# --- What is accepted -------------------------------------------------------


def test_a_form_gives_back_the_image_and_the_language_pair(uploads_client: TestClient) -> None:
    image = jpeg(1280, 720)

    response = uploads_client.post(PATH, **form(image))

    assert response.status_code == 200
    assert response.json() == {
        "bytes": len(image),
        "filename": "frame.jpg",
        "media_type": "image/jpeg",
        "source_language": "ml-IN",
        "target_language": "en-IN",
    }


def test_a_png_is_read_as_a_png(uploads_client: TestClient) -> None:
    response = uploads_client.post(PATH, **form(png(800, 600), media_type="image/png"))

    assert response.json()["media_type"] == "image/png"
    assert response.json()["filename"] == "frame.png"


def test_the_bytes_decide_the_format_and_not_the_caller(uploads_client: TestClient) -> None:
    """A caller that labels its PNG a JPEG still sends a PNG to the provider."""
    response = uploads_client.post(PATH, **form(png(800, 600), media_type="image/jpeg"))

    assert response.json()["media_type"] == "image/png"


def test_the_name_the_caller_gave_its_file_is_never_passed_on(
    uploads_client: TestClient,
) -> None:
    """A name chosen by whoever sent the request has no place in a request we make."""
    response = uploads_client.post(PATH, **form(png(10, 10), filename="../../etc/passwd"))

    assert response.json()["filename"] == "frame.png"


def test_the_language_codes_lose_the_spaces_around_them(uploads_client: TestClient) -> None:
    response = uploads_client.post(PATH, **form(jpeg(10, 10), source_language=" ml-IN "))

    assert response.json()["source_language"] == "ml-IN"


def test_a_frame_of_two_megabytes_is_never_written_to_a_file(
    uploads_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gotcha this endpoint exists under: a camera image stays in memory.

    The form parser moves a file part out of memory and into a temporary file
    by calling `rollover`. For an accepted upload it must never do so.
    """
    rollovers: list[str] = []
    rollover = SpooledTemporaryFile.rollover

    def spy(self: SpooledTemporaryFile[bytes]) -> None:
        rollovers.append("rolled")
        rollover(self)

    monkeypatch.setattr(SpooledTemporaryFile, "rollover", spy)

    response = uploads_client.post(PATH, **form(padded(jpeg(1280, 720), 2 * 1024 * 1024)))

    assert response.status_code == 200
    assert response.json()["bytes"] == 2 * 1024 * 1024
    assert rollovers == [], "the frame must stay in the request's memory"


# --- The cap ----------------------------------------------------------------


def test_an_image_just_past_the_cap_is_refused(uploads_client: TestClient) -> None:
    response = uploads_client.post(PATH, **form(padded(jpeg(1280, 720), MAX_IMAGE_BYTES + 1)))

    assert response.status_code == 413
    assert response.json() == {
        "error": {"code": "image_too_large", "message": "The image must be 5 MB or smaller."}
    }


def test_a_body_far_past_the_cap_is_refused(uploads_client: TestClient) -> None:
    response = uploads_client.post(PATH, **form(padded(jpeg(1280, 720), 2 * MAX_IMAGE_BYTES)))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "image_too_large"


def test_an_image_at_the_cap_is_accepted(uploads_client: TestClient) -> None:
    response = uploads_client.post(PATH, **form(padded(jpeg(1280, 720), MAX_IMAGE_BYTES)))

    assert response.status_code == 200
    assert response.json()["bytes"] == MAX_IMAGE_BYTES


# --- What is refused --------------------------------------------------------


@pytest.mark.parametrize(
    ("posted", "why"),
    [
        (form(b"GIF89a" + b"\x00" * 32), "a format the contract does not accept"),
        (form(b""), "an empty file"),
        (form(None), "no image at all"),
        (form(jpeg(10, 10), source_language=None), "no source language"),
        (form(jpeg(10, 10), target_language=None), "no target language"),
        (form(jpeg(10, 10), source_language="   "), "a blank source language"),
    ],
)
def test_a_form_that_is_not_a_frame_to_translate_is_refused(
    uploads_client: TestClient, posted: dict[str, Any], why: str
) -> None:
    response = uploads_client.post(PATH, **posted)

    assert response.status_code == 400, why
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_json_body_is_refused(uploads_client: TestClient) -> None:
    response = uploads_client.post(PATH, json={"source_language": "ml-IN"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert "multipart" in response.json()["error"]["message"]


def test_a_multipart_body_that_cannot_be_read_is_refused(uploads_client: TestClient) -> None:
    response = uploads_client.post(
        PATH,
        content=b"not a multipart body at all",
        headers={"content-type": "multipart/form-data; boundary=whatever"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_multipart_body_with_no_boundary_is_refused(uploads_client: TestClient) -> None:
    response = uploads_client.post(
        PATH,
        content=b"--x--\r\n",
        headers={"content-type": "multipart/form-data"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
