"""Reading one frame to translate out of a multipart form, in memory.

`POST /v1/frames/translate` is sent a multipart form: the cropped image as a
file, the source and target language as fields. This module turns that request
into those three values, and refuses anything that is not one of them — before
configuration is read and long before a provider is called.

Two rules shape it, and both come from the design:

* **The image never reaches a disk.** It is a photograph of whatever the person
  is pointing their camera at, so it lives in the request's memory and is
  discarded with the response (design decision D5). The form parser holds a
  file part in memory only until it grows past a size of its own, so that size
  is lifted above the cap here: an upload this module accepts is never written
  anywhere.
* **There is a cap.** The contract accepts an image of 5 MB. The body is read
  in chunks and abandoned the moment it passes that cap plus a little room for
  the form's two small fields and its boundaries, so an upload far too large
  costs the backend only what it had already read.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import Request
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from .errors import ApiError
from .images import JPEG_MEDIA_TYPE, PNG_MEDIA_TYPE, image_media_type

#: The contract's cap on the uploaded image.
MAX_IMAGE_BYTES = 5 * 1024 * 1024

#: Room for the two language fields, the part headers and the boundaries. The
#: form has three small parts beside the image, so this is generous.
FORM_OVERHEAD_BYTES = 8 * 1024

#: The whole request body a cap-sized image can arrive in.
MAX_BODY_BYTES = MAX_IMAGE_BYTES + FORM_OVERHEAD_BYTES

IMAGE_FIELD = "image"
SOURCE_FIELD = "source_language"
TARGET_FIELD = "target_language"

MULTIPART_MEDIA_TYPE = "multipart/form-data"

#: What the crop is called when it is passed on to the recognition provider.
#: The name the caller gave its own file is never reused: a name chosen by
#: whoever sent the request has no business in a request we make.
FILENAMES = {PNG_MEDIA_TYPE: "frame.png", JPEG_MEDIA_TYPE: "frame.jpg"}


@dataclass(frozen=True)
class FrameUpload:
    """One frame to translate: the image, and the pair of languages for it."""

    image: bytes
    filename: str
    media_type: str
    source_language: str
    target_language: str


class _InMemoryParser(MultiPartParser):
    """The form parser, holding the image in memory instead of in a file.

    Starlette spools a file part into a temporary file once it passes
    `spool_max_size`. Every body this module accepts is smaller than the cap,
    so lifting that size past the cap means an accepted image stays in memory
    from the moment it arrives to the moment the response goes back.
    """

    spool_max_size = MAX_BODY_BYTES + 1


async def read_frame_upload(request: Request) -> FrameUpload:
    """The frame in this request, or the one error shape saying what was wrong.

    Raises `ApiError` with `image_too_large` (413) for an image past the cap,
    and with `invalid_request` (400) for a body that is not a frame to
    translate at all. Nothing here reads configuration or calls a provider.
    """
    form = await _parse(request)
    try:
        image = await _image(form)
        source_language = _text(form, SOURCE_FIELD)
        target_language = _text(form, TARGET_FIELD)
    finally:
        # Frees the parser's hold on the parts. The image bytes are ours by
        # now, and they are the only copy of the frame anywhere.
        await form.close()

    media_type = image_media_type(image)
    if media_type is None:
        raise _refused(f"The {IMAGE_FIELD} must be a PNG or a JPEG.")
    return FrameUpload(
        image=image,
        filename=FILENAMES[media_type],
        media_type=media_type,
        source_language=source_language,
        target_language=target_language,
    )


async def _parse(request: Request) -> FormData:
    """Read the body under the cap and parse it as the multipart form it must be."""
    if MULTIPART_MEDIA_TYPE not in request.headers.get("content-type", "").lower():
        raise _refused(
            "This endpoint takes a multipart form: an image, a source language "
            "and a target language."
        )
    body = await _body_within_cap(request)

    async def stream() -> AsyncGenerator[bytes, None]:
        yield body

    try:
        # One file and a handful of fields is the whole form; more than that is
        # not a frame to translate, whatever else it might be.
        return await _InMemoryParser(request.headers, stream(), max_files=1, max_fields=4).parse()
    except MultiPartException as exc:
        raise _refused(f"The multipart form could not be read: {exc.message}") from exc


async def _body_within_cap(request: Request) -> bytes:
    """The request body, abandoned the moment it passes the cap.

    A caller that declares its length is refused before it sends anything; one
    that does not is refused as soon as what has arrived is too much. Either
    way the backend never holds more than a cap-sized body.
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise _too_large()

    chunks: list[bytes] = []
    read = 0
    async for chunk in request.stream():
        read += len(chunk)
        if read > MAX_BODY_BYTES:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)


async def _image(form: FormData) -> bytes:
    part = form.get(IMAGE_FIELD)
    if not isinstance(part, UploadFile):
        raise _refused(f"The form needs an {IMAGE_FIELD} file: the cropped frame to translate.")
    data = await part.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise _too_large()
    if not data:
        raise _refused(f"The {IMAGE_FIELD} file is empty.")
    return data


def _text(form: FormData, name: str) -> str:
    value = form.get(name)
    if not isinstance(value, str) or not value.strip():
        raise _refused(f"The form needs a non-empty {name}.")
    return value.strip()


def _refused(message: str) -> ApiError:
    return ApiError(400, "invalid_request", message, log_fields={"reason": "malformed_upload"})


def _too_large() -> ApiError:
    megabytes = MAX_IMAGE_BYTES // (1024 * 1024)
    return ApiError(
        413,
        "image_too_large",
        f"The image must be {megabytes} MB or smaller.",
        log_fields={"limit_bytes": MAX_IMAGE_BYTES},
    )
