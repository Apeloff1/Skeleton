"""Tests for the 2026-08-30 SOTA upgrade modules.

Covers the three additions from the social-media SOTA sweep:
plane_weights (adaptive RRF weights), memory/eviction (workflow-aware
cache pressure), cortex/sleep_prior (utility-prioritized replay).
"""

from __future__ import annotations

import pytest

from skeleton.retrieval.plane_weights import PlaneWeightLearner
from skeleton.memory.eviction import evict_for_capacity, keep_score
from skeleton.memory.warmer import Filler, FillerStore
from skeleton.cortex.sleep_prior import attach_priority_replay, trace_priority
from skeleton.cortex.sleep import SleepCycle
from skeleton.cortex.port import Thought


# ── PlaneWeightLearner ───────────────────────────────────────────────────

def test_learner_starts_at_base_weights():
    lw = PlaneWeightLearner({"rag": 1.0, "cag": 1.4})
    w = lw.effective_weights()
    assert w["cag"] == 1.4 and w["mag"] == 1.0


def test_used_plane_gains_weight_unused_sinks():
    lw = PlaneWeightLearner()
    for _ in range(10):
        lw.observe(["rag"])
    w = lw.effective_weights()
    assert w["rag"] > w["mag"]
    assert w["mag"] >= 0.3  # floor holds — no plane starves to zero


def test_weights_bounded_and_stats_track():
    lw = PlaneWeightLearner()
    for _ in range(50):
        lw.observe(["kag"])
    w = lw.effective_weights()
    assert all(0.3 <= v <= 2.0 for v in w.values())
    assert lw.stats()["updates"] == 50


def test_learner_rejects_bad_lr():
    with pytest.raises(ValueError):
        PlaneWeightLearner(lr=2.0)


# ── Workflow-aware eviction ──────────────────────────────────────────────

def _filler(key, tokens=100, refreshed_at=0.0):
    return Filler(key=key, sha="s", text="t", tokens=tokens, ttl_s=3600,
                  built_at=0.0, refreshed_at=refreshed_at)


def test_keep_score_prefers_hot_fresh_expensive():
    cold = _filler("cold", tokens=100, refreshed_at=0.0)
    hot = _filler("hot", tokens=40_000, refreshed_at=1e12)
    assert keep_score(hot, now=1e12, hits=50) > keep_score(cold, now=1e12)


def test_evict_for_capacity_drops_cheapest_first():
    store = FillerStore()
    store.put(_filler("cheap", tokens=100))
    store.put(_filler("pricey", tokens=40_000, refreshed_at=1e12))
    evicted = evict_for_capacity(store, capacity=1, now=1e12,
                                 hit_counts={"pricey": 30})
    assert evicted == ["cheap"]
    assert store.get("pricey") is not None


def test_evict_is_deterministic_on_ties():
    store = FillerStore()
    store.put(_filler("b", tokens=100))
    store.put(_filler("a", tokens=100))
    evicted = evict_for_capacity(store, capacity=1, now=1e12)
    assert evicted == ["a"]  # name tiebreak


# ── Prioritized sleep replay ─────────────────────────────────────────────

def test_trace_priority_scales_with_conf_and_slack():
    sc = SleepCycle()
    low = sc.record("low", [0.0] * 8)
    hi = sc.record("hi", [0.0] * 8,
                   left=Thought(slot="left", kind="x", text="t",
                                confidence=0.9, numbers=(1.0, 2.0, 3.0)),
                   slack=0.8)
    assert trace_priority(hi) > trace_priority(low)


def test_attach_priority_replay_orders_buffer():
    sc = SleepCycle()
    sc.record("low", [0.0] * 8)
    sc.record("high", [0.0] * 8, slack=1.0,
              left=Thought(slot="left", kind="x", text="t", confidence=1.0,
                           numbers=(1.0, 2.0, 3.0)))
    attach_priority_replay(sc)
    assert list(sc.buffer)[0].stim == "high"
