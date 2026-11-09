from __future__ import annotations

import struct

from app.images import PNG_SIGNATURE, image_dimensions, image_media_type


def png(width: int, height: int) -> bytes:
    """The header of a PNG that is `width` by `height` — enough for the size."""
    return (
        PNG_SIGNATURE
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


def jpeg(width: int, height: int, *, with_metadata: bool = True) -> bytes:
    """A JPEG start-of-frame, optionally behind a JFIF metadata segment."""
    app0 = (
        b"\xff\xe0"
        + struct.pack(">H", 16)
        + b"JFIF\x00"
        + b"\x01\x01\x00"
        + b"\x00\x01\x00\x01"
        + b"\x00\x00"
    )
    sof0 = (
        b"\xff\xc0"
        + struct.pack(">H", 17)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x03"
        + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )
    return b"\xff\xd8" + (app0 if with_metadata else b"") + sof0 + b"\xff\xd9"


def test_a_png_reports_its_size() -> None:
    assert image_dimensions(png(1280, 720)) == (1280, 720)


def test_a_jpeg_reports_its_size() -> None:
    assert image_dimensions(jpeg(1280, 720)) == (1280, 720)


def test_a_jpeg_size_is_found_behind_its_metadata() -> None:
    """A phone's JPEG carries segments before the frame; the size is still there."""
    assert image_dimensions(jpeg(640, 480, with_metadata=False)) == (640, 480)


def test_a_progressive_jpeg_reports_its_size() -> None:
    frame = jpeg(800, 600).replace(b"\xff\xc0", b"\xff\xc2", 1)

    assert image_dimensions(frame) == (800, 600)


def test_an_unknown_format_reports_nothing() -> None:
    assert image_dimensions(b"GIF89a....") is None


def test_a_truncated_png_reports_nothing() -> None:
    assert image_dimensions(png(100, 100)[:20]) is None


def test_a_jpeg_with_no_frame_reports_nothing() -> None:
    assert image_dimensions(b"\xff\xd8\xff\xd9") is None


def test_a_zero_sized_image_reports_nothing() -> None:
    """A width of zero would make normalising the region hint a division by zero."""
    assert image_dimensions(png(0, 100)) is None


# --- Which of the two formats an upload is ---------------------------------


def test_a_png_is_named_as_one() -> None:
    assert image_media_type(png(10, 10)) == "image/png"


def test_a_jpeg_is_named_as_one() -> None:
    assert image_media_type(jpeg(10, 10)) == "image/jpeg"


def test_a_format_the_contract_does_not_accept_is_named_as_nothing() -> None:
    """The frame endpoint refuses these rather than spending a recognition call."""
    assert image_media_type(b"GIF89a" + b"\x00" * 32) is None
    assert image_media_type(b"") is None
