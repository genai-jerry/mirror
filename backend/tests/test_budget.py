"""The shared recognition allowance: granted, deferred, or refused.

Two kinds of test live here. The ones that prove *when* a call is granted run
on a clock that only moves when the budget sleeps, so a minute passes
instantly and nothing depends on how fast the machine is. The ones that prove
many users share one allowance need real concurrency, so they run on the real
clock with the minute shortened to a fraction of a second.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest

from app.budget import (
    DEFAULT_MAX_WAIT_SECONDS,
    DEFAULT_RECOGNITION_PER_MINUTE,
    RECOGNITION_DEFERRED_EVENT,
    BudgetLimits,
    RateBudget,
    parse_limits,
    recognition_budget,
)
from app.config import ConfigError, load_config, write_override
from app.errors import ApiError
from app.logging_setup import configure_logging
from app.main import create_app
from app.settings import Settings


class Clock:
    """A monotonic clock that only moves when the budget waits."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)


def budget_file(settings: Settings, **fields: Any) -> None:
    """Put a whole budget file in the override directory, as an operator would."""
    payload = {
        "recognition_per_minute": 60,
        "translation_per_minute": 30,
        "max_wait_seconds": 15,
        **fields,
    }
    write_override("budget", payload, settings)


def on_a_fake_clock(settings: Settings) -> tuple[RateBudget, Clock]:
    clock = Clock()
    return recognition_budget(settings, monotonic=clock, sleep=clock.sleep), clock


def lines(captured: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in captured.strip().splitlines() if line.strip()]


async def test_a_call_inside_the_allowance_is_granted_at_once(settings: Settings) -> None:
    budget, clock = on_a_fake_clock(settings)

    await budget.acquire()

    assert clock.now == 0.0
    assert budget.granted_in_window() == 1


async def test_a_call_past_the_allowance_waits_for_the_minute_to_slide(
    settings: Settings,
) -> None:
    budget_file(settings, recognition_per_minute=2, max_wait_seconds=60)
    budget, clock = on_a_fake_clock(settings)

    await budget.acquire()
    await budget.acquire()
    assert clock.now == 0.0

    await budget.acquire()

    # The two calls of the first minute have left the window, so the third got
    # the slot the oldest of them gave back — a minute after it was granted.
    assert clock.now == 60.0
    assert budget.granted_in_window() == 1


async def test_the_wait_deadline_refuses_the_request(settings: Settings) -> None:
    budget_file(settings, recognition_per_minute=1, max_wait_seconds=5)
    budget, clock = on_a_fake_clock(settings)
    await budget.acquire()

    with pytest.raises(ApiError) as refusal:
        await budget.acquire()

    error = refusal.value
    assert error.status_code == 429
    assert error.code == "budget_exhausted"
    # 55 seconds of the granted call's minute were still to run.
    assert error.headers["Retry-After"] == "55"
    assert error.log_fields == {"limit": 1, "waited_seconds": 5.0, "retry_after": 55}
    assert clock.now == 5.0


async def test_a_refused_request_leaves_the_queue(settings: Settings) -> None:
    budget_file(settings, recognition_per_minute=1, max_wait_seconds=0)
    budget, _ = on_a_fake_clock(settings)
    await budget.acquire()

    with pytest.raises(ApiError):
        await budget.acquire()

    assert budget.waiting == 0


async def test_a_changed_budget_file_changes_the_allowance_without_a_restart(
    settings: Settings,
) -> None:
    budget_file(settings, recognition_per_minute=1, max_wait_seconds=0)
    budget, clock = on_a_fake_clock(settings)
    await budget.acquire()
    with pytest.raises(ApiError):
        await budget.acquire()

    budget_file(settings, recognition_per_minute=5, max_wait_seconds=0)

    # The same running budget, nothing restarted: the next call is granted
    # because the file now allows five a minute. This is DS-3's low budget
    # arriving at a backend that is already serving.
    await budget.acquire()
    assert clock.now == 0.0
    assert budget.granted_in_window() == 2


async def test_a_request_already_waiting_picks_up_a_raised_allowance(
    settings: Settings,
) -> None:
    """The allowance is read on every pass, not once when the request arrived.

    An operator who raises the budget — or the system test plan's DS-3 set
    being unloaded again — reaches the requests already in the queue, not only
    the ones that arrive afterwards.
    """
    budget_file(settings, recognition_per_minute=1, max_wait_seconds=5)
    clock = Clock()
    raised = False

    async def sleep_and_raise_the_allowance(seconds: float) -> None:
        nonlocal raised
        if not raised:
            budget_file(settings, recognition_per_minute=2, max_wait_seconds=5)
            raised = True
        await clock.sleep(seconds)

    budget = recognition_budget(settings, monotonic=clock, sleep=sleep_and_raise_the_allowance)
    await budget.acquire()

    # The allowance of one is spent, so this request queues. While it waits the
    # file comes to allow two, and the next pass grants it on the spot — rather
    # than refusing it at the five-second deadline under the old number.
    await budget.acquire()

    assert raised
    assert clock.now == 5.0
    assert budget.granted_in_window() == 2


async def test_a_lowered_allowance_defers_instead_of_exceeding_the_new_limit(
    settings: Settings,
) -> None:
    """DS-3's low budget reaching a backend that has already served calls.

    Four calls go out ten seconds apart under a budget of sixty a minute, and
    then the budget comes down to two. The minute already holds four, so the
    next call waits for enough of them to leave it. The new limit is never
    exceeded: the backend defers.
    """
    budget_file(settings, recognition_per_minute=60, max_wait_seconds=60)
    budget, clock = on_a_fake_clock(settings)
    for _ in range(4):
        await budget.acquire()
        clock.now += 10.0
    assert budget.granted_in_window() == 4

    budget_file(settings, recognition_per_minute=2, max_wait_seconds=60)

    await budget.acquire()

    # Granted at eighty seconds: the moment the third-oldest call left the
    # minute and took the count inside the new allowance of two.
    assert clock.now == 80.0
    assert budget.granted_in_window() == 2


async def test_a_deferred_request_is_logged_with_the_wait_depth(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    budget_file(settings, recognition_per_minute=1, max_wait_seconds=0)
    budget, _ = on_a_fake_clock(settings)
    await budget.acquire()
    configure_logging()
    capsys.readouterr()

    with pytest.raises(ApiError):
        await budget.acquire()

    (deferred,) = [
        line for line in lines(capsys.readouterr().out) if line["event"] == "recognition.deferred"
    ]
    assert deferred["waiting"] == 1
    assert deferred["limit"] == 1
    assert RECOGNITION_DEFERRED_EVENT == "recognition.deferred"


async def test_many_callers_never_exceed_the_allowance(settings: Settings) -> None:
    """The real concurrency the system test plan leaves to this suite.

    Six requests arrive at once on one budget of two calls a minute. The minute
    is a third of a second here, so the test is the shape of ST-6 rather than
    its two real minutes.
    """
    window = 0.3
    budget_file(settings, recognition_per_minute=2, max_wait_seconds=30)
    budget = recognition_budget(settings, window_seconds=window)
    granted: list[float] = []

    async def one_call() -> None:
        await budget.acquire()
        granted.append(time.monotonic())

    await asyncio.gather(*(one_call() for _ in range(6)))

    assert len(granted) == 6
    for moment in granted:
        in_the_same_minute = [other for other in granted if moment - window < other <= moment]
        assert len(in_the_same_minute) <= 2, granted
    # Six calls at two a minute take two further minutes to clear.
    assert granted[-1] - granted[0] >= 2 * window


async def test_requests_are_granted_in_the_order_they_arrived(settings: Settings) -> None:
    window = 0.2
    budget_file(settings, recognition_per_minute=1, max_wait_seconds=30)
    budget = recognition_budget(settings, window_seconds=window)
    order: list[str] = []

    async def one_call(name: str) -> None:
        await budget.acquire()
        order.append(name)

    waiting = []
    for name in ("first", "second", "third"):
        waiting.append(asyncio.create_task(one_call(name)))
        # Let the task reach the queue, so the arrival order is the one the
        # names say rather than whatever the event loop happened to do.
        await asyncio.sleep(0)
    await asyncio.gather(*waiting)

    assert order == ["first", "second", "third"]


async def test_a_budget_file_the_service_cannot_use_is_refused(settings: Settings) -> None:
    budget_file(settings, recognition_per_minute=0)
    budget, _ = on_a_fake_clock(settings)

    with pytest.raises(ApiError) as refusal:
        await budget.acquire()

    assert refusal.value.status_code == 500
    assert refusal.value.code == "invalid_configuration"
    assert "recognition budget" in refusal.value.message


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("recognition_per_minute", 0),
        ("recognition_per_minute", 1.5),
        ("recognition_per_minute", "2"),
        ("recognition_per_minute", True),
        ("max_wait_seconds", -1),
        ("max_wait_seconds", "15"),
        ("max_wait_seconds", None),
    ],
)
def test_an_unusable_value_is_named(field: str, value: Any) -> None:
    with pytest.raises(ConfigError, match=field):
        parse_limits(
            {"recognition_per_minute": 60, "max_wait_seconds": 15, field: value},
            limit_field="recognition_per_minute",
            default_limit=DEFAULT_RECOGNITION_PER_MINUTE,
        )


def test_a_file_that_leaves_a_value_out_uses_the_shipped_number() -> None:
    limits = parse_limits(
        {"recognition_per_minute": 3},
        limit_field="recognition_per_minute",
        default_limit=DEFAULT_RECOGNITION_PER_MINUTE,
    )

    assert limits == BudgetLimits(calls_per_minute=3, max_wait_seconds=DEFAULT_MAX_WAIT_SECONDS)


def test_the_shipped_budget_file_and_the_numbers_in_code_agree(settings: Settings) -> None:
    shipped = load_config("budget", settings)

    assert shipped["recognition_per_minute"] == DEFAULT_RECOGNITION_PER_MINUTE
    assert shipped["max_wait_seconds"] == DEFAULT_MAX_WAIT_SECONDS


def test_the_allowance_in_force_is_read_from_configuration(settings: Settings) -> None:
    budget_file(settings, recognition_per_minute=2, max_wait_seconds=7)
    budget = recognition_budget(settings)

    assert budget.limits() == BudgetLimits(calls_per_minute=2, max_wait_seconds=7.0)


def test_each_app_holds_one_recognition_budget(settings: Settings) -> None:
    one = create_app(settings)
    another = create_app(settings)

    assert isinstance(one.state.recognition_budget, RateBudget)
    assert one.state.recognition_budget.window_seconds == 60.0
    # Every request of one app draws on that app's single budget; a second app
    # (a second test, or a second process) starts with its own.
    assert one.state.recognition_budget is not another.state.recognition_budget
