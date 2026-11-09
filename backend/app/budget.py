"""The shared allowance for outgoing recognition calls.

The recognition provider allows so many calls a minute, and every person using
the app draws on that one allowance (design decision D8). This module is the
queue in front of it: a call is granted while fewer than
`recognition_per_minute` calls have been granted in the last minute, and a call
past that waits its turn — in the order the requests arrived — for up to
`max_wait_seconds`. Past that the caller is refused with 429
`budget_exhausted` and a `Retry-After`, which the app's overlay behaviour (it
keeps the last good translation) makes invisible to the person. The provider's
limit is never exceeded: the backend defers instead.

The minute slides. It is the last sixty seconds, not a minute of the clock, so
a burst at the end of one minute cannot be followed straight away by another at
the start of the next.

A slot is spent when it is granted and nothing gives it back: by then the call
has gone out, and whether the provider answered or failed does not change that
the allowance paid for it.

Both numbers come from the `budget` configuration file, read on every pass
(design decision D6), so an operator's change — and the system test plan's
low-budget set, DS-3 — takes effect on the next request with no restart. A
value the budget cannot use is named rather than guessed at; the admin surface
checks a whole file before it stores one, so only a file put into the override
directory by hand arrives here wrong.

One application holds one budget (`app.state.recognition_budget`), and the
service runs as one process in v1 — that is what makes the allowance shared
across every user rather than per request. Scaling out means moving this count
out of process, which the design names as a later change. Nothing here takes a
lock: every change to the queue happens on the event loop's own thread,
between awaits.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from .config import ConfigError, load_config
from .errors import ApiError
from .logging_setup import log_event
from .settings import Settings

CONFIG_NAME = "budget"

#: The "minute" of per-minute. A test shortens it; nothing else does.
WINDOW_SECONDS = 60.0

RECOGNITION_LIMIT_FIELD = "recognition_per_minute"
RECOGNITION_DEFERRED_EVENT = "recognition.deferred"

#: What the shipped `budget.json` says, for a hand-written override file that
#: leaves a value out — an override replaces the shipped file rather than
#: merging into it, so the value has to come from somewhere.
DEFAULT_RECOGNITION_PER_MINUTE = 60
DEFAULT_MAX_WAIT_SECONDS = 15.0


@dataclass(frozen=True)
class BudgetLimits:
    """What the budget file allows right now."""

    calls_per_minute: int
    max_wait_seconds: float


def parse_limits(
    raw: Mapping[str, Any],
    *,
    limit_field: str,
    default_limit: int,
    default_max_wait: float = DEFAULT_MAX_WAIT_SECONDS,
) -> BudgetLimits:
    """Read one budget file's numbers, or refuse it naming the key that is wrong."""
    if not isinstance(raw, Mapping):
        raise ConfigError("the budget configuration must be a JSON object")
    return BudgetLimits(
        calls_per_minute=_calls(raw, limit_field, default_limit),
        max_wait_seconds=_seconds(raw, "max_wait_seconds", default_max_wait),
    )


class RateBudget:
    """A sliding one-minute allowance with a queue of waiting requests.

    Recognition is the one budget this epic needs (`recognition_budget` below).
    The name of the limit, the name of its log event and the number to fall back
    on are constructor arguments so that a second kind of call — translation has
    a per-minute number in the same file — becomes one more factory function
    rather than a second copy of the queue.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        name: str,
        limit_field: str,
        default_limit: int,
        deferred_event: str,
        window_seconds: float = WINDOW_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.settings = settings
        self.name = name
        self.limit_field = limit_field
        self.default_limit = default_limit
        self.deferred_event = deferred_event
        self.window_seconds = window_seconds
        self._monotonic = monotonic
        self._sleep = sleep or asyncio.sleep
        # When each call of the last minute was granted, oldest first.
        self._granted: deque[float] = deque()
        # One ticket per request waiting for a slot, in the order they arrived.
        self._queue: deque[object] = deque()

    @property
    def waiting(self) -> int:
        """How many requests are queued for a slot right now."""
        return len(self._queue)

    def limits(self) -> BudgetLimits:
        """The allowance in force right now, read from configuration.

        Raises `ConfigError` for a file the budget cannot use.
        """
        raw = load_config(CONFIG_NAME, self.settings)
        return parse_limits(
            raw,
            limit_field=self.limit_field,
            default_limit=self.default_limit,
        )

    def granted_in_window(self) -> int:
        """How many calls have been granted in the last minute."""
        now = self._monotonic()
        self._forget_calls_before(now - self.window_seconds)
        return len(self._granted)

    async def acquire(self) -> None:
        """Take a slot in this minute's allowance, waiting in turn for one.

        Returns when the call may go out. Raises `ApiError` with
        `budget_exhausted` (429) when the wait deadline passes first, and with
        `invalid_configuration` (500) when the budget file cannot be read.
        """
        ticket = object()
        self._queue.append(ticket)
        started = self._monotonic()
        said_deferred = False
        try:
            while True:
                limits = self._limits_or_refuse()
                now = self._monotonic()
                self._forget_calls_before(now - self.window_seconds)
                first_in_line = self._queue[0] is ticket
                if first_in_line and len(self._granted) < limits.calls_per_minute:
                    self._granted.append(now)
                    return
                if not said_deferred:
                    log_event(
                        self.deferred_event,
                        waiting=len(self._queue),
                        limit=limits.calls_per_minute,
                    )
                    said_deferred = True
                deadline = started + limits.max_wait_seconds
                if now >= deadline:
                    raise self._exhausted(now, limits, waited=now - started)
                # Until the oldest call leaves the window and hands its slot
                # back, and never past this request's own deadline. A zero wait
                # is a request that is not first in line yet: it stands aside
                # and lets the one ahead of it take the slot.
                await self._sleep(max(min(self._free_at(now), deadline) - now, 0.0))
        finally:
            self._queue.remove(ticket)

    def _limits_or_refuse(self) -> BudgetLimits:
        try:
            return self.limits()
        except ConfigError as exc:
            # Only a file edited past the admin endpoint can get here: that
            # endpoint refuses a configuration the service cannot use. The
            # operator needs the detail, the app does not.
            log_event(
                "config.invalid",
                level=logging.ERROR,
                message=str(exc),
                name=CONFIG_NAME,
            )
            raise ApiError(
                500,
                "invalid_configuration",
                f"The backend's {self.name} budget configuration cannot be read.",
            ) from exc

    def _forget_calls_before(self, horizon: float) -> None:
        """Drop the calls that have left the window; their slots are back."""
        while self._granted and self._granted[0] <= horizon:
            self._granted.popleft()

    def _free_at(self, now: float) -> float:
        """When the oldest call in the window leaves it and its slot comes back."""
        if not self._granted:
            return now
        return self._granted[0] + self.window_seconds

    def _exhausted(self, now: float, limits: BudgetLimits, *, waited: float) -> ApiError:
        retry_after = max(1, math.ceil(self._free_at(now) - now))
        return ApiError(
            429,
            "budget_exhausted",
            f"The backend's {self.name} allowance of {limits.calls_per_minute} calls a "
            f"minute is used up. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
            log_fields={
                "limit": limits.calls_per_minute,
                "waited_seconds": round(waited, 3),
                "retry_after": retry_after,
            },
        )


def recognition_budget(settings: Settings, **overrides: Any) -> RateBudget:
    """The budget every outgoing recognition call draws on."""
    return RateBudget(
        settings,
        name="recognition",
        limit_field=RECOGNITION_LIMIT_FIELD,
        default_limit=DEFAULT_RECOGNITION_PER_MINUTE,
        deferred_event=RECOGNITION_DEFERRED_EVENT,
        **overrides,
    )


def recognition_budget_of(request: Request) -> RateBudget:
    """The recognition allowance this app was built with — see `app.main.create_app`.

    One per application, so every request draws on the same one: that is what
    makes the allowance shared across every user rather than per request.
    """
    budget: RateBudget = request.app.state.recognition_budget
    return budget


def _calls(raw: Mapping[str, Any], field: str, default: int) -> int:
    value = raw.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(
            f"{field} is {value!r}, which is not a whole number of calls of at least 1"
        )
    return value


def _seconds(raw: Mapping[str, Any], field: str, default: float) -> float:
    value = raw.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ConfigError(f"{field} is {value!r}, which is not a number of seconds of 0 or more")
    return float(value)
