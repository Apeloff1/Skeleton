"""Tests for wave 5: traffic splitter, experiment tracker, lock manager,
DR planner, and profiler.
"""
from __future__ import annotations

import random
import time

import pytest

from skeleton.core.lock_manager import LockManager
from skeleton.intelligence.experiment_tracker import ExperimentTracker
from skeleton.mesh.traffic_splitter import TrafficSplitter
from skeleton.observability.profiler import Profiler
from skeleton.reliability.dr_planner import DRPlanner


class TestTrafficSplitter:
    def test_weighted_routing(self):
        splitter = TrafficSplitter(rng=random.Random(7))
        splitter.add_backend("v1", weight=90)
        splitter.add_backend("v2", weight=10)
        picks = [splitter.route() for _ in range(200)]
        assert picks.count("v1") > picks.count("v2")

    def test_sticky_sessions(self):
        splitter = TrafficSplitter(rng=random.Random(1))
        splitter.add_backend("a", 50)
        splitter.add_backend("b", 50)
        first = splitter.route(session_id="s1")
        for _ in range(10):
            assert splitter.route(session_id="s1") == first

    def test_unhealthy_excluded(self):
        splitter = TrafficSplitter(rng=random.Random(1))
        splitter.add_backend("a", 100)
        splitter.add_backend("b", 100)
        splitter.mark_health("a", False)
        for _ in range(20):
            assert splitter.route() == "b"

    def test_auto_rebalance(self):
        splitter = TrafficSplitter()
        splitter.add_backend("bad", 100)
        for _ in range(25):
            splitter.record("bad", 50.0, error=True)
        actions = splitter.auto_rebalance()
        assert actions and actions[0]["new_weight"] < actions[0]["old_weight"]

    def test_shadow_logging(self):
        splitter = TrafficSplitter()
        splitter.add_backend("primary", 100)
        splitter.add_backend("candidate", 0)
        splitter.enable_shadow("candidate")
        splitter.record("primary", 42.0)
        assert splitter.card()["shadow_events"] == 1


class TestExperimentTracker:
    def test_deterministic_assignment(self):
        tracker = ExperimentTracker()
        tracker.create("exp1")
        a1 = tracker.assign("exp1", "user-1")
        a2 = tracker.assign("exp1", "user-1")
        assert a1 == a2

    def test_assignment_distribution(self):
        tracker = ExperimentTracker()
        tracker.create("exp2", weights=[50, 50])
        assigns = [tracker.assign("exp2", f"u{i}") for i in range(200)]
        assert "control" in assigns and "treatment" in assigns

    def test_significance_detected(self):
        tracker = ExperimentTracker()
        tracker.create("exp3")
        for i in range(100):
            tracker.record("exp3", "control", 0.5 + (i % 3) * 0.01)
            tracker.record("exp3", "treatment", 0.9 + (i % 3) * 0.01)
        result = tracker.significance("exp3")
        assert result["significant"]

    def test_conclude_declares_winner(self):
        tracker = ExperimentTracker()
        tracker.create("exp4")
        for i in range(50):
            tracker.record("exp4", "control", 1.0)
            tracker.record("exp4", "treatment", 2.0)
        result = tracker.conclude("exp4")
        assert result["concluded"]
        assert result["winner"] == "treatment"

    def test_insufficient_samples(self):
        tracker = ExperimentTracker()
        tracker.create("exp5")
        tracker.record("exp5", "control", 1.0)
        result = tracker.significance("exp5")
        assert not result["significant"]


class TestLockManager:
    def test_acquire_release(self):
        lm = LockManager()
        lock = lm.acquire("res", "holder-1")
        assert lock is not None
        assert lm.release("res", "holder-1", lock["token"])

    def test_contention_blocked(self):
        lm = LockManager()
        lm.acquire("res", "h1")
        assert lm.acquire("res", "h2") is None

    def test_fencing_token(self):
        lm = LockManager()
        lock = lm.acquire("res", "h1")
        assert lm.validate_token("res", lock["token"])
        assert not lm.validate_token("res", 999)

    def test_wrong_token_release_fails(self):
        lm = LockManager()
        lm.acquire("res", "h1")
        assert not lm.release("res", "h1", 999)

    def test_expiry_allows_reacquire(self):
        lm = LockManager(default_ttl_s=0.01)
        lm.acquire("res", "h1")
        time.sleep(0.02)
        lock = lm.acquire("res", "h2")
        assert lock is not None

    def test_reentrant_refresh(self):
        lm = LockManager()
        first = lm.acquire("res", "h1")
        second = lm.acquire("res", "h1")
        assert second["refreshed"]
        assert second["token"] == first["token"]


class TestDRPlanner:
    def test_drill_all_pass(self):
        dr = DRPlanner()
        dr.set_objective("db", rpo_s=3600, rto_s=60, tier="critical")
        dr.add_runbook("db-restore", "db failure", "db", steps=[lambda: True, lambda: True])
        result = dr.run_drill("db-restore", last_backup_age_s=300)
        d = result.to_dict()
        assert d["passed"]
        assert d["rto_met"] and d["rpo_met"]

    def test_drill_step_failure(self):
        dr = DRPlanner()
        dr.set_objective("api", rpo_s=60, rto_s=30)
        dr.add_runbook("api-restart", "api crash", "api", steps=[lambda: True, lambda: False])
        result = dr.run_drill("api-restart")
        assert not result.to_dict()["passed"]

    def test_rpo_breach(self):
        dr = DRPlanner()
        dr.set_objective("db", rpo_s=60, rto_s=60)
        dr.add_runbook("rb", "x", "db", steps=[lambda: True])
        result = dr.run_drill("rb", last_backup_age_s=9999)
        assert not result.rpo_met

    def test_coverage_gaps(self):
        dr = DRPlanner()
        dr.set_objective("db", 60, 60)
        dr.set_objective("api", 60, 60)
        dr.add_runbook("db-only", "x", "db", steps=[lambda: True])
        coverage = dr.coverage()
        assert "api" in coverage["coverage_gaps"]


class TestProfiler:
    def test_profile_records(self):
        prof = Profiler()
        result = prof.profile("op", lambda: 42)
        assert result == 42
        assert prof.stats("op")["samples"] == 1

    def test_percentiles(self):
        prof = Profiler()
        for i in range(100):
            prof.record("x", float(i))
        stats = prof.stats("x")
        assert stats["p50_ms"] == 50.0
        assert stats["max_ms"] == 99.0

    def test_regression_tracking(self):
        prof = Profiler()
        for _ in range(10):
            prof.record("y", 100.0)
        prof.set_baseline("y")
        for _ in range(10):
            prof.record("y", 200.0)
        stats = prof.stats("y")
        assert stats["regression_pct"] == 50.0

    def test_hot_paths(self):
        prof = Profiler()
        for _ in range(5):
            prof.record("slow", 500.0)
            prof.record("fast", 1.0)
        hot = prof.hot_paths(2)
        assert hot[0]["name"] == "slow"

    def test_folded_stacks(self):
        prof = Profiler()
        prof.record("z", 12.5)
        folded = prof.folded_stacks("z")
        assert "z 12.500" in folded
