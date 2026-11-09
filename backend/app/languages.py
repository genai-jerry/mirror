"""What languages the service supports, and which provider serves each one.

`languages.json` (design decision D6) is the single answer to three questions:
which source languages the picker offers, which target languages it offers,
and which provider entry reads and translates each source language. Provider
entries have *names*, and every provider call is logged with the name it used
— that is how an operator sees that a configuration change took effect.

The file is read through `app.config`, so an operator's override answers in
place of the shipped file and a change takes effect on the next request with no
restart. Nothing here is remembered between calls: the provider for a language
is resolved from configuration every time it is needed.

Language codes are BCP-47 (`ml-IN`, `en-IN`) and are compared without regard to
case, as the standard says; the spelling the configuration uses is the spelling
the endpoint returns.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import ConfigError, load_config
from .settings import Settings

CONFIG_NAME = "languages"


class _Coded(Protocol):
    """Anything configuration names by a language code."""

    code: str


@dataclass(frozen=True)
class Provider:
    """One named way of reading or translating text."""

    name: str
    kind: str
    model: str | None = None


@dataclass(frozen=True)
class TargetLanguage:
    """A language the app may translate into."""

    code: str
    name: str


@dataclass(frozen=True)
class SourceLanguage:
    """A language the app may read, and the provider entries that serve it."""

    code: str
    name: str
    recognition_provider: str
    translation_provider: str


@dataclass(frozen=True)
class LanguageConfig:
    """One reading of `languages.json`, already checked over."""

    sources: tuple[SourceLanguage, ...] = ()
    targets: tuple[TargetLanguage, ...] = ()
    providers: Mapping[str, Provider] = field(default_factory=dict)

    def source(self, code: str) -> SourceLanguage | None:
        return _by_code(self.sources, code)

    def target(self, code: str) -> TargetLanguage | None:
        return _by_code(self.targets, code)

    def supports(self, source_code: str, target_code: str) -> bool:
        """Whether this pair is offered. The frame endpoint rejects pairs that are not."""
        return self.source(source_code) is not None and self.target(target_code) is not None

    def recognition_provider_for(self, source_code: str) -> Provider:
        """The provider entry configured to read `source_code` right now."""
        return self._provider(self._source_or_raise(source_code).recognition_provider)

    def translation_provider_for(self, source_code: str) -> Provider:
        """The provider entry configured to translate `source_code` right now."""
        return self._provider(self._source_or_raise(source_code).translation_provider)

    def picker_payload(self) -> dict[str, list[dict[str, str]]]:
        """What `GET /v1/languages` answers: codes and names, and nothing else.

        Provider names are the backend's business and stay in the backend.
        """
        return {
            "sources": [{"code": item.code, "name": item.name} for item in self.sources],
            "targets": [{"code": item.code, "name": item.name} for item in self.targets],
        }

    def _source_or_raise(self, source_code: str) -> SourceLanguage:
        found = self.source(source_code)
        if found is None:
            raise ConfigError(f"source language {source_code} is not configured")
        return found

    def _provider(self, name: str) -> Provider:
        provider = self.providers.get(name)
        if provider is None:  # pragma: no cover - parsing rejects this configuration
            raise ConfigError(f"provider {name} is not configured")
        return provider


def load_language_config(settings: Settings) -> LanguageConfig:
    """The language configuration in force right now."""
    return parse_language_config(load_config(CONFIG_NAME, settings))


def parse_language_config(raw: Mapping[str, Any]) -> LanguageConfig:
    """Check a whole languages file over and turn it into a `LanguageConfig`.

    Raises `ConfigError` naming what is wrong, so an operator who sends a file
    the service cannot use is told why instead of having it stored. A file that
    lists nothing is not wrong: it means the service offers no languages yet.
    """
    if not isinstance(raw, Mapping):
        raise ConfigError("the language configuration must be a JSON object")
    providers = _parse_providers(raw.get("providers", {}))
    return LanguageConfig(
        sources=_parse_sources(raw.get("sources", []), providers),
        targets=_parse_targets(raw.get("targets", [])),
        providers=providers,
    )


def _parse_providers(raw: Any) -> dict[str, Provider]:
    if not isinstance(raw, Mapping):
        raise ConfigError("providers must be a JSON object of name to provider")
    providers: dict[str, Provider] = {}
    for name, entry in raw.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("every provider needs a non-empty name")
        where = f"provider {name}"
        if not isinstance(entry, Mapping):
            raise ConfigError(f"{where} must be a JSON object")
        providers[name] = Provider(
            name=name,
            kind=_text(entry, "kind", where),
            model=_optional_text(entry, "model", where),
        )
    return providers


def _parse_sources(raw: Any, providers: Mapping[str, Provider]) -> tuple[SourceLanguage, ...]:
    sources: list[SourceLanguage] = []
    for entry in _entries(raw, "sources"):
        code = _text(entry, "code", "every source language")
        where = f"source language {code}"
        source = SourceLanguage(
            code=code,
            name=_text(entry, "name", where),
            recognition_provider=_text(entry, "recognition_provider", where),
            translation_provider=_text(entry, "translation_provider", where),
        )
        for role, provider_name in (
            ("recognition_provider", source.recognition_provider),
            ("translation_provider", source.translation_provider),
        ):
            if provider_name not in providers:
                raise ConfigError(
                    f"{where} names {role} {provider_name}, which is not in providers"
                )
        sources.append(source)
    _reject_duplicates(item.code for item in sources)
    return tuple(sources)


def _parse_targets(raw: Any) -> tuple[TargetLanguage, ...]:
    targets: list[TargetLanguage] = []
    for entry in _entries(raw, "targets"):
        code = _text(entry, "code", "every target language")
        targets.append(TargetLanguage(code=code, name=_text(entry, "name", f"language {code}")))
    _reject_duplicates(item.code for item in targets)
    return tuple(targets)


def _entries(raw: Any, name: str) -> Sequence[Mapping[str, Any]]:
    if not isinstance(raw, list):
        raise ConfigError(f"{name} must be a JSON list")
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise ConfigError(f"every entry in {name} must be a JSON object")
    return raw


def _text(entry: Mapping[str, Any], field: str, where: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where} needs a non-empty {field}")
    return value.strip()


def _optional_text(entry: Mapping[str, Any], field: str, where: str) -> str | None:
    if entry.get(field) is None:
        return None
    return _text(entry, field, where)


def _reject_duplicates(codes: Iterable[str]) -> None:
    seen: set[str] = set()
    for code in codes:
        folded = code.casefold()
        if folded in seen:
            raise ConfigError(f"language {code} is configured twice")
        seen.add(folded)


def _by_code[Coded: _Coded](items: tuple[Coded, ...], code: str) -> Coded | None:
    wanted = code.strip().casefold()
    for item in items:
        if item.code.casefold() == wanted:
            return item
    return None
