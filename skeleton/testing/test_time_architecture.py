from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

import pytest

from skeleton.foundation.time import Deadline, Duration, Instant, ManualClock


def instant(monotonic: float, wall: datetime | None = None) -> Instant:
    return Instant(monotonic, wall or datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_elapsed_time_uses_monotonic_clock_not_wall_clock() -> None:
    start = instant(10.0)
    end = instant(15.0, start.utc - timedelta(days=30))
    assert end.elapsed_since(start) == Duration(5.0)


def test_deadline_ignores_wall_clock_jump() -> None:
    clock = ManualClock(instant(100.0))
    deadline = Deadline.after(clock.now(), Duration(10.0))
    clock.set_wall_time(clock.now().utc + timedelta(days=365))
    assert not deadline.expired(clock.now())
    assert deadline.remaining(clock.now()) == Duration(10.0)
    clock.advance(Duration(10.0))
    assert deadline.expired(clock.now())


def test_manual_clock_is_deterministic_and_injectable() -> None:
    clock = ManualClock(instant(7.0))
    first = clock.now()
    second = clock.advance(Duration(2.5))
    assert second.monotonic_seconds == 9.5
    assert second.utc - first.utc == timedelta(seconds=2.5)


def test_naive_and_non_utc_wall_times_fail_closed() -> None:
    with pytest.raises(ValueError):
        Instant(1.0, datetime(2026, 1, 1))
    plus_one = timezone(timedelta(hours=1))
    with pytest.raises(ValueError):
        Instant(1.0, datetime(2026, 1, 1, tzinfo=plus_one))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, -1.0])
def test_invalid_duration_fails_closed(value: float) -> None:
    with pytest.raises(ValueError):
        Duration(value)


def test_backwards_monotonic_elapsed_fails_closed() -> None:
    with pytest.raises(ValueError):
        instant(1.0).elapsed_since(instant(2.0))


def test_deadline_boundary_is_expired() -> None:
    now = instant(5.0)
    deadline = Deadline.after(now, Duration(0.0))
    assert deadline.expired(now)
    assert deadline.remaining(now) == Duration(0.0)
