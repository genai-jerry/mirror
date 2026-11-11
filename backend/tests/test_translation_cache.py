"""The translation cache: what it answers, and for how long."""

from __future__ import annotations

from app.translation_cache import (
    DEFAULT_LIFETIME_SECONDS,
    TranslationCache,
    cache_key,
    normalise,
)

HEADLINE = "കേരളത്തിൽ മഴ തുടരുന്നു"
ENGLISH = "Rain continues in Kerala"


class Clock:
    """A clock that moves only when a test says so."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def key(
    text: str = HEADLINE,
    *,
    source: str = "ml-IN",
    target: str = "en-IN",
    provider: str = "sarvam-translate",
) -> str:
    return cache_key(text, source_language=source, target_language=target, provider=provider)


# --- The key ---------------------------------------------------------------


def test_the_same_text_and_languages_make_the_same_key() -> None:
    assert key() == key()


def test_the_same_headline_split_differently_is_one_entry() -> None:
    """Recognition joins blocks with newlines, and may split them differently."""
    assert key(f"{HEADLINE}\nരണ്ടാം വരി") == key(f"{HEADLINE}  രണ്ടാം\tവരി")


def test_a_different_provider_entry_is_a_different_key() -> None:
    """ST-8: the newly configured entry cannot answer with the old one's work."""
    assert key(provider="sarvam-translate") != key(provider="sarvam-translate-alt")


def test_a_different_target_language_is_a_different_key() -> None:
    assert key(target="en-IN") != key(target="hi-IN")


def test_a_different_source_language_is_a_different_key() -> None:
    """The same characters read as another language are another translation."""
    assert key(source="ml-IN") != key(source="hi-IN")


def test_a_language_code_in_another_case_is_the_same_language() -> None:
    assert key(source="ml-IN") == key(source="ml-in")


def test_the_key_does_not_hold_the_text() -> None:
    """What a person pointed their camera at is not kept in readable form."""
    assert HEADLINE not in key()


def test_whitespace_is_collapsed_to_single_spaces() -> None:
    assert normalise("  two \n\t lines  ") == "two lines"


# --- Answering -------------------------------------------------------------


def test_nothing_is_answered_before_anything_is_stored() -> None:
    assert TranslationCache().get(key()) is None


def test_what_was_stored_is_what_is_answered() -> None:
    cache = TranslationCache()

    cache.put(key(), ENGLISH, lifetime_seconds=DEFAULT_LIFETIME_SECONDS)

    assert cache.get(key()) == ENGLISH


def test_an_entry_is_forgotten_once_its_lifetime_has_passed() -> None:
    clock = Clock()
    cache = TranslationCache(monotonic=clock)
    cache.put(key(), ENGLISH, lifetime_seconds=600.0)

    clock.advance(599.0)
    assert cache.get(key()) == ENGLISH

    clock.advance(1.0)
    assert cache.get(key()) is None
    assert len(cache) == 0, "an expired entry is dropped as it is read"


def test_a_lifetime_of_nothing_stores_nothing() -> None:
    """How an operator switches the cache off without a code change."""
    cache = TranslationCache()

    cache.put(key(), ENGLISH, lifetime_seconds=0.0)

    assert cache.get(key()) is None


def test_storing_the_same_key_again_extends_its_lifetime() -> None:
    clock = Clock()
    cache = TranslationCache(monotonic=clock)
    cache.put(key(), ENGLISH, lifetime_seconds=600.0)

    clock.advance(500.0)
    cache.put(key(), ENGLISH, lifetime_seconds=600.0)
    clock.advance(500.0)

    assert cache.get(key()) == ENGLISH


def test_clearing_it_forgets_everything() -> None:
    cache = TranslationCache()
    cache.put(key(), ENGLISH, lifetime_seconds=600.0)

    cache.clear()

    assert cache.get(key()) is None


# --- Not growing without a limit -------------------------------------------


def test_expired_entries_make_room_for_new_ones() -> None:
    clock = Clock()
    cache = TranslationCache(max_entries=2, monotonic=clock)
    cache.put(key("first"), "one", lifetime_seconds=10.0)
    cache.put(key("second"), "two", lifetime_seconds=10.0)

    clock.advance(11.0)
    cache.put(key("third"), "three", lifetime_seconds=10.0)

    assert len(cache) == 1
    assert cache.get(key("third")) == "three"


def test_the_oldest_entry_goes_when_nothing_has_expired() -> None:
    cache = TranslationCache(max_entries=2)
    cache.put(key("first"), "one", lifetime_seconds=600.0)
    cache.put(key("second"), "two", lifetime_seconds=600.0)

    cache.put(key("third"), "three", lifetime_seconds=600.0)

    assert cache.get(key("first")) is None
    assert cache.get(key("second")) == "two"
    assert cache.get(key("third")) == "three"
