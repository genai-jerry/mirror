"""Turning recognized text into its translation, through the cache.

This is the one place that answers "what does this text say in the target
language": it reads the languages configuration to find which provider entry
translates this source language **right now**, asks the cache, and only calls
the provider when the cache has no answer. The frame translation endpoint uses
it and adds nothing of its own.

Two things follow from reading configuration on every call (design decision
D6). An operator who remaps a language to another provider entry sees the
change on the next request, with no restart (ST-8). And because the entry's
name is part of the cache key (`app.translation_cache`), the new entry starts
with no answers rather than repeating the old entry's.

How long an answer is kept is the `translation_cache_seconds` field of
`budget.json`, which holds the service's other timings; left out, entries live
ten minutes (D7). Setting it to zero switches the cache off.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from .config import ConfigError, load_config
from .errors import ApiError
from .languages import Provider, load_language_config
from .logging_setup import log_event
from .providers.sarvam_translate import SarvamTranslateClient
from .settings import Settings
from .translation_cache import (
    DEFAULT_LIFETIME_SECONDS,
    TranslationCache,
    cache_key,
    normalise,
)

BUDGET_CONFIG_NAME = "budget"
LIFETIME_FIELD = "translation_cache_seconds"


@dataclass(frozen=True)
class Translation:
    """One answer: the text, who translated it, and whether it was already known."""

    text: str
    provider: str | None
    cached: bool


class Translator:
    """Translation of recognized text, with the cache in front of the provider.

    One per app (`app.main.create_app` holds it on the app's state), because
    the cache it owns is this process's whole cache — see D7.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        cache: TranslationCache | None = None,
        client_factory: Callable[[Provider, Settings], SarvamTranslateClient] | None = None,
    ) -> None:
        self.settings = settings
        self.cache = cache if cache is not None else TranslationCache()
        self._client_factory = client_factory or _client_for

    async def translate(
        self,
        text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> Translation:
        """Translate `text` from `source_language` into `target_language`.

        Raises `ApiError` with `unsupported_language` (400) when the source
        language is no longer configured, and with `provider_error` (502) when
        the provider cannot answer. Text with nothing in it is answered with
        nothing: no configuration is read and no provider is called, which is
        the blank wall of the API contract.
        """
        prepared = normalise(text)
        if not prepared:
            return Translation(text="", provider=None, cached=False)

        provider = self._provider_for(source_language)
        key = cache_key(
            prepared,
            source_language=source_language,
            target_language=target_language,
            provider=provider.name,
        )
        remembered = self.cache.get(key)
        if remembered is not None:
            log_event("translation.cache_hit")
            return Translation(text=remembered, provider=provider.name, cached=True)

        client = self._client_factory(provider, self.settings)
        translated = await client.translate(
            prepared,
            source_language=source_language,
            target_language=target_language,
        )
        self.cache.put(key, translated, lifetime_seconds=self.lifetime_seconds())
        return Translation(text=translated, provider=provider.name, cached=False)

    def lifetime_seconds(self) -> float:
        """How long a new entry answers for, as configuration says right now.

        A missing field is the default. So is a value an operator typed wrongly
        — the admin endpoint refuses one of those, so only a file edited past
        it can get here, and a cache lifetime is not worth failing a person's
        translation over. Either way one line says what was found.
        """
        try:
            budget = load_config(BUDGET_CONFIG_NAME, self.settings)
        except ConfigError as exc:
            log_event(
                "config.invalid",
                level=logging.WARNING,
                message=str(exc),
                name=BUDGET_CONFIG_NAME,
                field=LIFETIME_FIELD,
            )
            return DEFAULT_LIFETIME_SECONDS
        value = budget.get(LIFETIME_FIELD)
        if value is None:
            return DEFAULT_LIFETIME_SECONDS
        if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
            log_event(
                "config.invalid",
                level=logging.WARNING,
                message=(
                    f"{LIFETIME_FIELD} is set to {value!r}, which is not a number of "
                    f"seconds; translations are kept for {DEFAULT_LIFETIME_SECONDS:.0f} "
                    "seconds instead"
                ),
                name=BUDGET_CONFIG_NAME,
                field=LIFETIME_FIELD,
            )
            return DEFAULT_LIFETIME_SECONDS
        return float(value)

    def _provider_for(self, source_language: str) -> Provider:
        """The provider entry configured to translate `source_language` now.

        The frame endpoint checks the language pair before anything else, so a
        source language missing here means configuration changed in between.
        The answer is the same either way, and it names the code the way the
        contract does.
        """
        try:
            config = load_language_config(self.settings)
        except ConfigError as exc:
            log_event(
                "config.invalid",
                level=logging.ERROR,
                message=str(exc),
                name="languages",
            )
            raise ApiError(
                500,
                "invalid_configuration",
                "The backend's language configuration cannot be read.",
            ) from exc
        if config.source(source_language) is None:
            raise ApiError(
                400,
                "unsupported_language",
                f"source language {source_language} is not configured",
                log_fields={"language": source_language},
            )
        try:
            return config.translation_provider_for(source_language)
        except ConfigError as exc:  # pragma: no cover - parsing rejects this configuration
            raise ApiError(500, "invalid_configuration", str(exc)) from exc


def translator_of(request: Request) -> Translator:
    """The translator this app was built with — see `app.main.create_app`."""
    translator: Translator = request.app.state.translator
    return translator


def _client_for(provider: Provider, settings: Settings) -> SarvamTranslateClient:
    """The client that speaks this provider entry's kind.

    One kind translates in v1, so there is nothing to choose between yet; a
    language mapped to an entry of any other kind is refused by the client
    itself, which is where that check belongs.
    """
    return SarvamTranslateClient.from_provider(provider, settings)
