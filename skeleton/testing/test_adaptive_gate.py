"""Tests for skeleton.kernel.adaptive_gate (gameforge-rs AdaptiveGate port)."""

from __future__ import annotations

import time

from skeleton.kernel.adaptive_gate import AdaptiveGate, Verdict


def test_admit_under_capacity():
    g = AdaptiveGate(capacity=5, refill_per_sec=0)
    for _ in range(5):
        assert g.admit(priority=1) is Verdict.ADMITTED
    stats = g.stats()
    assert stats["admitted"] == 5
    assert stats["shed"] == 0
    assert stats["tokens_available"] == 0
    assert stats["capacity"] == 5


def test_shed_bulk_when_empty():
    g = AdaptiveGate(capacity=2, refill_per_sec=0)
    assert g.admit(priority=2) is Verdict.ADMITTED
    assert g.admit(priority=2) is Verdict.ADMITTED
    assert g.admit(priority=2) is Verdict.SHED
    assert g.admit(priority=1) is Verdict.SHED
    stats = g.stats()
    assert stats["admitted"] == 2
    assert stats["shed"] == 2


def test_priority_zero_overdraw_when_empty():
    g = AdaptiveGate(capacity=1, refill_per_sec=0)
    assert g.admit(priority=1) is Verdict.ADMITTED
    assert g.stats()["tokens_available"] == 0
    # Priority 0 (control plane) may still admit when tokens==0
    assert g.admit(priority=0) is Verdict.ADMITTED
    assert g.admit(priority=0) is Verdict.ADMITTED
    # Bulk still shed
    assert g.admit(priority=3) is Verdict.SHED
    stats = g.stats()
    assert stats["admitted"] == 3
    assert stats["shed"] == 1
    assert stats["tokens_available"] == 0


def test_stats_counters():
    g = AdaptiveGate(capacity=3, refill_per_sec=0)
    g.admit(1)
    g.admit(1)
    g.admit(1)
    g.admit(1)  # shed
    s = g.stats()
    assert s == {
        "tokens_available": 0,
        "capacity": 3,
        "admitted": 3,
        "shed": 1,
    }


def test_refill_restores_tokens():
    g = AdaptiveGate(capacity=2, refill_per_sec=100)
    g.admit(1)
    g.admit(1)
    assert g.admit(1) is Verdict.SHED
    time.sleep(0.05)  # ~5 tokens worth at 100/s, capped at capacity
    assert g.admit(1) is Verdict.ADMITTED
