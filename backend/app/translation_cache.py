"""The short-lived store of text this service has already translated.

Design decision D7: entries live in this process's memory for a configurable
lifetime (ten minutes by default) and nowhere else. The camera sends the same
headline every few seconds while a person holds the phone still, so the cache
only has to answer "this text again, within a session" — which memory does for
free, and empties by itself.

An entry is found by a key that holds everything the translation depended on:
the recognized text with its whitespace collapsed, the source and target
language, and the **name of the provider entry** that would translate it. The
provider name is part of the key because remapping a language to another
provider entry must take effect on the next request (ST-8): the new entry
cannot read the old entry's answers.

The text itself is not kept. The key is a SHA-256 of it, so what a person
pointed their camera at is not sitting in this process in readable form.

Consequence, stated plainly: the cache is per-process, so the backend runs as
one instance in v1. A second replica would hold a second cache and translate
the same headline again — correct, but twice the provider calls.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock

#: How long an entry answers for when configuration does not say (D7).
DEFAULT_LIFETIME_SECONDS = 600.0

#: How many entries one process keeps. A headline is small, and expiry empties
#: the cache on its own; this only stops a backend that has been running for
#: weeks in front of a changing scene from growing without a limit.
DEFAULT_MAX_ENTRIES = 1024

# What the parts of a key are joined with before they are hashed. A newline
# cannot appear in any of them — the text has had its whitespace collapsed —
# so two different sets of parts can never make one string.
_SEPARATOR = "\n"


def cache_key(
    text: str,
    *,
    source_language: str,
    target_language: str,
    provider: str,
) -> str:
    """The key the translation of `text` is stored under.

    Language codes are compared without regard to case, as BCP-47 says and as
    `app.languages` already does, so `ml-IN` and `ml-in` are one language here
    too. The text is not folded: a headline in capitals is not the same text.
    """
    parts = (
        normalise(text),
        source_language.strip().casefold(),
        target_language.strip().casefold(),
        provider,
    )
    return sha256(_SEPARATOR.join(parts).encode("utf-8")).hexdigest()


def normalise(text: str) -> str:
    """The text with every run of whitespace collapsed to one space.

    Recognition joins the blocks it found with newlines, and the same headline
    read twice can be split into blocks differently. Collapsing whitespace is
    what makes those two readings one cache entry — and it is the text that is
    sent to the provider, so the key and the request always agree.
    """
    return " ".join(text.split())


@dataclass(frozen=True)
class _Entry:
    """One translation, and the moment it stops being answered with."""

    translation: str
    expires_at: float


class TranslationCache:
    """Translations this process has made, for as long as they are still good.

    Safe to share: a request may be answered on the event loop or on a worker
    thread, so every reader and writer takes one lock, exactly as
    `app.config` does for the configuration it remembers.
    """

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._entries: dict[str, _Entry] = {}
        self._max_entries = max_entries
        self._monotonic = monotonic
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        """The translation stored under `key`, or None when there is none left.

        An entry past its lifetime is dropped as it is read, so an expired
        answer is never given and nothing has to sweep the cache.
        """
        now = self._monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._entries[key]
                return None
            return entry.translation

    def put(self, key: str, translation: str, *, lifetime_seconds: float) -> None:
        """Store `translation` under `key` for the next `lifetime_seconds`.

        A lifetime of zero or less stores nothing: that is how an operator
        switches the cache off without a code change.
        """
        if lifetime_seconds <= 0:
            return
        now = self._monotonic()
        with self._lock:
            if key not in self._entries and len(self._entries) >= self._max_entries:
                self._prune(now)
            self._entries[key] = _Entry(translation=translation, expires_at=now + lifetime_seconds)

    def clear(self) -> None:
        """Forget everything. The next identical text is translated again."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _prune(self, now: float) -> None:
        """Make room: drop what has expired, and if nothing had, the oldest.

        Called with the lock held. Dictionaries keep insertion order, so the
        first key is the one stored longest ago.
        """
        for key in [key for key, entry in self._entries.items() if entry.expires_at <= now]:
            del self._entries[key]
        while len(self._entries) >= self._max_entries:
            del self._entries[next(iter(self._entries))]
