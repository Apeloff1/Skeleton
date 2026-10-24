"""#807 B071: deterministic time for replay/perf gates."""
from __future__ import annotations

import math

import pytest

from skeleton.quality.deterministic_time import (
    SCHEMA_ID,
    DeterministicClock,
    as_monotonic,
    budget_within,
)


def test_schema_id() -> None:
    assert SCHEMA_ID == "quality.deterministic_time.v1"


def test_thawed_clock_ticks_per_read_in_seconds() -> None:
    clock = DeterministicClock(tick_ms=10.0)
    assert clock() == 0.0
    assert clock() == pytest.approx(0.010)
    assert clock.elapsed_ms() == pytest.approx(20.0)


def test_frozen_clock_never_advances_until_explicit_advance() -> None:
    clock = DeterministicClock().freeze()
    assert clock() == clock() == 0.0
    clock.advance(5.0)
    assert clock.elapsed_ms() == 5.0
    clock.thaw()
    clock()
    assert clock.elapsed_ms() == pytest.approx(5.0 + 16.667)


def test_two_clocks_are_bit_identical() -> None:
    a, b = DeterministicClock(), DeterministicClock()
    assert [a() for _ in range(100)] == [b() for _ in range(100)]


@pytest.mark.parametrize("bad", [-1.0, math.inf, math.nan])
def test_rejects_invalid_steps(bad: float) -> None:
    with pytest.raises(ValueError):
        DeterministicClock(tick_ms=bad)
    with pytest.raises(ValueError):
        DeterministicClock().advance(bad)


def test_budget_within_fails_closed() -> None:
    assert budget_within(16.0, 16.667)
    assert budget_within(16.667, 16.667)
    assert not budget_within(17.0, 16.667)
    assert not budget_within(math.nan, 16.667)
    assert not budget_within(-1.0, 16.667)
    assert not budget_within("x", 16.667)  # type: ignore[arg-type]
    assert budget_within(1e9, None)


def test_as_monotonic_defaults_to_frozen_deterministic_clock() -> None:
    clock = as_monotonic()
    assert isinstance(clock, DeterministicClock) and clock.frozen
    custom = lambda: 1.0  # noqa: E731
    assert as_monotonic(custom) is custom
    with pytest.raises(TypeError):
        as_monotonic(42)  # type: ignore[arg-type]
