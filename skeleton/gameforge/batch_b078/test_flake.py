from datetime import date

import pytest

from skeleton.gameforge.batch_b078 import FlakeError, FlakeTracker, RunRecord
from skeleton.gameforge.batch_b078.flake import wilson_lower


def _feed(t, tid, outcomes, seed=1):
    for ok in outcomes:
        t.record(RunRecord(tid, "abc", seed, ok))


def test_detects_statistical_flake():
    t = FlakeTracker()
    _feed(t, "test_ai", [True] * 15 + [False] * 5)
    _feed(t, "test_ok", [True] * 20)
    _feed(t, "test_broken", [False] * 20)
    assert set(t.flaky()) == {"test_ai"}


def test_different_seeds_are_not_flake():
    t = FlakeTracker(min_runs=1)
    _feed(t, "test_x", [True], seed=1)
    _feed(t, "test_x", [False], seed=2)
    assert t.flaky() == {}


def test_too_few_runs_not_flagged():
    t = FlakeTracker()
    _feed(t, "t", [True, False])
    assert t.flaky() == {}
    assert wilson_lower(0, 10) == 0.0


def test_quarantine_requires_owner_and_expiry_and_expires():
    t = FlakeTracker()
    _feed(t, "test_ai", [True] * 10 + [False] * 10)
    d = date(2026, 10, 31)
    with pytest.raises(FlakeError):
        t.quarantine_test("test_ai", " ", "r", d, 3)
    with pytest.raises(FlakeError):
        t.quarantine_test("test_ai", "oystein", "r", d, 30)
    with pytest.raises(FlakeError):
        t.quarantine_test("test_ok", "oystein", "r", d, 3)
    t.quarantine_test("test_ai", "oystein", "timing", d, 3)
    assert t.is_quarantined("test_ai", date(2026, 11, 2))
    assert t.enforce(date(2026, 11, 2)) == []
    exp = t.enforce(date(2026, 11, 3))
    assert [e.owner for e in exp] == ["oystein"] and not t.is_quarantined("test_ai", date(2026, 11, 3))
