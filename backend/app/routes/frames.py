"""`POST /v1/frames/translate` — the one endpoint the app calls.

A cropped frame goes in; the text in it, that text's translation and where the
text sits go out. Every piece of the work is already built — reading the upload
(`app.uploads`), what languages are offered (`app.languages`), the shared
recognition allowance (`app.budget`), recognition (`app.recognition`) and
translation through the cache (`app.translation`). This module is the order
they run in, and nothing else:

1. the app token, where an operator has switched one on (design decision D10);
2. the upload — a multipart form, under the size cap, a PNG or a JPEG;
3. the language pair, against configuration: refused here, before any provider
   is called at all (system test ST-9);
4. a slot in the recognition allowance — taken in turn, or refused with 429
   (design decision D8);
5. recognition;
6. a frame with no text in it: an answer with nothing in it, and no
   translation call (ST-10);
7. translation, answered from the cache when this text has been seen lately
   (ST-5).

The image is in the request's memory and is discarded with the response.
Nothing of the frame is stored: the only thing kept is the translation cache's
entry, which holds text and no image.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from ..auth import require_app_token, settings_of
from ..budget import recognition_budget_of
from ..languages import load_language_config_or_refuse, require_configured_pair
from ..providers.sarvam_parse import Region
from ..recognition import recognition_client_for
from ..translation import translator_of
from ..uploads import read_frame_upload

router = APIRouter(prefix="/v1", tags=["frames"])


@router.post("/frames/translate", dependencies=[Depends(require_app_token)])
async def translate_frame(request: Request) -> dict[str, Any]:
    """Recognize the text in one cropped frame and answer with its translation."""
    settings = settings_of(request)
    upload = await read_frame_upload(request)
    require_configured_pair(
        load_language_config_or_refuse(settings),
        upload.source_language,
        upload.target_language,
    )

    # Resolved before the slot is taken, because resolving it is reading
    # configuration rather than calling anybody: a provider entry an operator
    # has mistyped should not spend an allowance nothing used.
    recognizer = recognition_client_for(upload.source_language, settings)
    await recognition_budget_of(request).acquire()
    recognized = await recognizer.recognize(
        upload.image,
        language=upload.source_language,
        filename=upload.filename,
        content_type=upload.media_type,
    )
    if not recognized.text.strip():
        # A blank wall. The app draws nothing for it, so there is nothing to
        # translate and no region to point at.
        return _answer("", "", None, cached=False)

    translation = await translator_of(request).translate(
        recognized.text,
        source_language=upload.source_language,
        target_language=upload.target_language,
    )
    return _answer(
        recognized.text,
        translation.text,
        recognized.region_hint,
        cached=translation.cached,
    )


def _answer(
    recognized_text: str,
    translated_text: str,
    region: Region | None,
    *,
    cached: bool,
) -> dict[str, Any]:
    """The 200 body of the API contract."""
    return {
        "recognized_text": recognized_text,
        "translated_text": translated_text,
        "region_hint": region.as_dict() if region is not None else None,
        "cached": cached,
    }
