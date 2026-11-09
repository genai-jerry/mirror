"""The pixel size of an uploaded image, read from its own header.

The region hint in the API contract is normalised 0-1 against the uploaded
image, so the recognition client has to know how wide and tall that image is.
Reading the header is enough for the two formats the contract accepts (PNG and
JPEG), and it keeps the backend free of an image-decoding dependency it would
otherwise need for nothing else.

Nothing here decodes pixels, and nothing here is written to disk: the bytes are
the request's own upload, already in memory (design decision D5).
"""

from __future__ import annotations

import struct

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# JPEG start-of-frame markers; every one of them carries the frame's size.
# C4 is the Huffman table and C8/CC are reserved, so they are not frames.
_JPEG_FRAME_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """`(width, height)` in pixels, or None when the bytes say nothing about it.

    None is an answer, not a failure: a caller that cannot learn the size
    leaves the region hint out rather than guessing at one.
    """
    if data.startswith(PNG_SIGNATURE):
        return _png_dimensions(data)
    if data.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(data)
    return None


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    """PNG puts width and height first, in the IHDR chunk."""
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return _checked(width, height)


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """JPEG puts the size in a start-of-frame segment, after any metadata."""
    index = 2
    end = len(data)
    while index + 3 < end:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xFF, 0x01) or 0xD0 <= marker <= 0xD9:
            index += 2
            continue
        (segment_length,) = struct.unpack(">H", data[index + 2 : index + 4])
        if segment_length < 2:
            return None
        if marker in _JPEG_FRAME_MARKERS:
            if index + 9 > end:
                return None
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return _checked(width, height)
        index += 2 + segment_length
    return None


def _checked(width: int, height: int) -> tuple[int, int] | None:
    if width <= 0 or height <= 0:
        return None
    return width, height
