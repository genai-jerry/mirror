"""Which client reads a source language, as configuration says right now.

`app.translation` is the matching module on the translation side: it answers
"what does this text say in English", and this one answers "who reads this
language". Both resolve the provider entry from configuration on every call
(design decision D6), so an operator who maps a language to another entry is
read by the next request, with no restart — and every `recognition.call` line
is logged against the entry's name, which is what an operator compares with
the file they edited.

The entry comes with the client: the recognition timeout and the poll interval
are optional fields of the provider entry, so the design's 12 seconds and 1
second are configuration too.
"""

from __future__ import annotations

from .config import ConfigError
from .errors import ApiError
from .languages import load_language_config_or_refuse, require_configured_source
from .providers.sarvam_parse import SarvamParseClient
from .settings import Settings


def recognition_client_for(source_language: str, settings: Settings) -> SarvamParseClient:
    """The client configuration says reads `source_language` right now.

    Raises `ApiError` with `unsupported_language` (400) when the language is
    not configured — the frame endpoint checks the pair before this, so that
    means configuration changed in between — and with `invalid_configuration`
    (500) when the file cannot be read.
    """
    config = load_language_config_or_refuse(settings)
    require_configured_source(config, source_language)
    try:
        provider = config.recognition_provider_for(source_language)
    except ConfigError as exc:  # pragma: no cover - parsing rejects this configuration
        raise ApiError(500, "invalid_configuration", str(exc)) from exc
    return SarvamParseClient.from_provider_entry(provider.name, provider.entry, settings)
