"""Sarvam translation: what the recognized text says in the target language.

One call, and it answers straight away (verified against docs.sarvam.ai, and
quoted in the design's "Contract with Sarvam"):

    POST https://api.sarvam.ai/translate
    {"input": ..., "source_language_code": ..., "target_language_code": ...,
     "model": ...}

The answer carries `translated_text`. The model is whatever the languages
configuration's provider entry names, which is what lets an operator remap a
language from one entry to another and see the change on the next request
(ST-8) — this client is built from the entry, per call, and holds nothing
between calls.

Each model caps how much text it will take: 1,000 characters for `mayura:v1`
and 2,000 for `sarvam-translate:v1`. Longer text is cut to the cap and one
warning line is logged, because a headline is a few dozen characters and
anything near the cap is a page the camera should not have been pointed at.

The API key is read from `app.settings` — that is, from the environment — and
goes nowhere but the request header: it is in no log line, no error message
and no response body.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from ..errors import ApiError
from ..languages import Provider
from ..logging_setup import log_event
from ..settings import Settings

PROVIDER_KIND = "sarvam_translate"
BASE_URL = "https://api.sarvam.ai"
API_KEY_HEADER = "api-subscription-key"

#: How long one translate call may take. Translation is synchronous and fast;
#: the app's own request timeout is twenty seconds, so this leaves the frame
#: endpoint room to answer rather than being cut off by its caller.
DEFAULT_TIMEOUT_SECONDS = 10.0

#: What each model will accept, per Sarvam's reference. A model this service
#: has not heard of gets the smaller cap, which every model accepts.
MODEL_INPUT_LIMITS = {
    "mayura:v1": 1000,
    "sarvam-translate:v1": 2000,
}
DEFAULT_INPUT_LIMIT = 1000

# What a provider body may contribute to a log line, so a page of HTML cannot
# turn one event into a screenful.
_BODY_SNIPPET = 300


class SarvamTranslateClient:
    """Translation through Sarvam's synchronous translate endpoint.

    One client per provider entry in the languages configuration; the entry's
    name is what every `translation.call` line is logged against, because that
    name is what a reader of the log compares with the configuration.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        provider_name: str = "sarvam-translate",
        model: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        base_url: str = BASE_URL,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.provider_name = provider_name
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")
        self._client_factory = client_factory or httpx.AsyncClient
        self._monotonic = monotonic

    @classmethod
    def from_provider(
        cls,
        provider: Provider,
        settings: Settings,
        **overrides: Any,
    ) -> SarvamTranslateClient:
        """Build the client the configuration's provider entry describes.

        The entry's `kind` has to be `sarvam_translate`; a language mapped to a
        recognition entry for its translation is an operator's configuration
        mistake, so it is named plainly rather than attempted.
        """
        if provider.kind != PROVIDER_KIND:
            raise ApiError(
                502,
                "provider_error",
                f"Translation provider {provider.name} is configured as "
                f"{provider.kind!r}, but this client only speaks {PROVIDER_KIND!r}.",
                log_fields={"provider": provider.name, "provider_kind": provider.kind},
            )
        return cls(
            settings,
            provider_name=provider.name,
            model=provider.model,
            **overrides,
        )

    @property
    def input_limit(self) -> int:
        """How many characters this client's model will take."""
        if self.model is None:
            return DEFAULT_INPUT_LIMIT
        return MODEL_INPUT_LIMITS.get(self.model, DEFAULT_INPUT_LIMIT)

    async def translate(self, text: str, *, source_language: str, target_language: str) -> str:
        """Translate `text`, or raise `ApiError` with `provider_error` (502).

        Everything Sarvam can do wrong — unreachable, slow, a failure status, a
        body this client cannot read — is one answer to the app, because there
        is one thing the app does about any of them: keep the overlay it has
        and try again on the next cycle.

        Text with nothing in it is not sent anywhere: the answer is empty too.
        """
        prepared = text.strip()
        if not prepared:
            return ""
        prepared = self._within_limit(prepared)

        api_key = self.settings.sarvam_api_key
        if not api_key:
            raise self._provider_error(
                "The translation provider is not configured: SARVAM_API_KEY is "
                "not set in the backend's environment.",
                reason="missing_api_key",
            )

        payload: dict[str, Any] = {
            "input": prepared,
            "source_language_code": source_language,
            "target_language_code": target_language,
        }
        if self.model is not None:
            payload["model"] = self.model

        log_event(
            "translation.call",
            provider=self.provider_name,
            model=self.model,
            characters=len(prepared),
        )
        body = self._json_body(
            await self._post(payload, headers={API_KEY_HEADER: api_key}),
        )
        translated = body.get("translated_text")
        if not isinstance(translated, str):
            raise self._provider_error(
                "The translation provider answered without a translation.",
                reason="no_translated_text",
            )
        return translated

    def _within_limit(self, text: str) -> str:
        """`text`, cut to what the model accepts, saying so once if it was cut."""
        limit = self.input_limit
        if len(text) <= limit:
            return text
        log_event(
            "translation.truncated",
            level=logging.WARNING,
            provider=self.provider_name,
            model=self.model,
            characters=len(text),
            limit=limit,
        )
        return text[:limit]

    async def _post(self, payload: dict[str, Any], *, headers: dict[str, str]) -> httpx.Response:
        """One call to the provider, inside this client's deadline."""
        try:
            async with self._client_factory() as client:
                response = await client.post(
                    f"{self.base_url}/translate",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            raise self._provider_error(
                "The translation provider did not answer in time.",
                reason="timeout",
                timeout_seconds=self.timeout_seconds,
            ) from exc
        except httpx.HTTPError as exc:
            raise self._provider_error(
                "The translation provider could not be reached.",
                reason=type(exc).__name__,
            ) from exc
        if response.status_code >= 400:
            raise self._provider_error(
                f"The translation provider answered with HTTP {response.status_code}.",
                reason="http_error",
                provider_status=response.status_code,
                provider_body=response.text[:_BODY_SNIPPET],
            )
        return response

    def _json_body(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise self._provider_error(
                "The translation provider answered with something that is not JSON.",
                reason="unreadable_body",
            ) from exc
        if not isinstance(body, dict):
            raise self._provider_error(
                "The translation provider answered with something that is not JSON.",
                reason="unreadable_body",
            )
        return body

    def _provider_error(self, message: str, **log_fields: Any) -> ApiError:
        return ApiError(
            502,
            "provider_error",
            message,
            log_fields={"provider": self.provider_name, **log_fields},
        )
