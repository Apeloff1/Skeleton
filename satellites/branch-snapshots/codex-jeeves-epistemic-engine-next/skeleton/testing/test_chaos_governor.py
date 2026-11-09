"""Tests for skeleton.kernel.chaos (gameforge-rs chaos::Governor port)."""

from __future__ import annotations

import time

from skeleton.kernel.chaos import ChaosGovernor, Rung


def test_rung_names_match_rs():
    assert Rung.NORMAL.name() == "normal"
    assert Rung.REDUCED_CACHING.name() == "reduced_caching"
    assert Rung.SHED_BACKGROUND.name() == "shed_background"
    assert Rung.STALE_READS.name() == "stale_reads"
    assert Rung.EMERGENCY_READ_ONLY.name() == "emergency_read_only"


def test_starts_normal_with_full_permits():
    g = ChaosGovernor(min_samples=4)
    assert g.rung() is Rung.NORMAL
    assert g.permits_writes() is True
    assert g.permits_background() is True
    assert g.should_cache() is True
    assert g.stats()["rung"] == "normal"


def test_min_samples_gates_escalation():
    g = ChaosGovernor(escalate_at=0.25, recover_at=0.05, min_samples=16, window_span=60.0)
    # 15 failures — below min_samples, must stay Normal
    for _ in range(15):
        g.observe(False)
    assert g.rung() is Rung.NORMAL


def test_escalate_on_high_error_rate():
    g = ChaosGovernor(escalate_at=0.25, recover_at=0.05, min_samples=16, window_span=60.0)
    # 8 fail / 16 = 0.5 > 0.25 → climb one rung
    for _ in range(8):
        g.observe(True)
    for _ in range(8):
        g.observe(False)
    assert g.rung() is Rung.REDUCED_CACHING
    assert g.should_cache() is False
    assert g.permits_background() is True
    assert g.permits_writes() is True


def test_escalate_through_rungs_and_permits_flip():
    # Each observe with a saturated high-error window climbs at most one rung.
    g = ChaosGovernor(escalate_at=0.1, recover_at=0.0, min_samples=4, window_span=60.0)
    for _ in range(4):
        g.observe(False)
    assert g.rung() is Rung.REDUCED_CACHING
    assert g.should_cache() is False
    assert g.permits_background() is True

    g.observe(False)
    assert g.rung() is Rung.SHED_BACKGROUND
    assert g.permits_background() is False
    assert g.permits_writes() is True

    g.observe(False)
    assert g.rung() is Rung.STALE_READS

    g.observe(False)
    assert g.rung() is Rung.EMERGENCY_READ_ONLY
    assert g.permits_writes() is False
    assert g.stats()["permits_writes"] is False


def test_recover_on_low_error_rate():
    g = ChaosGovernor(escalate_at=0.25, recover_at=0.05, min_samples=4, window_span=0.05)
    for _ in range(4):
        g.observe(False)
    assert g.rung() is Rung.REDUCED_CACHING
    time.sleep(0.06)  # age failures out of the window
    for _ in range(4):
        g.observe(True)
    assert g.rung() is Rung.NORMAL
    assert g.should_cache() is True
