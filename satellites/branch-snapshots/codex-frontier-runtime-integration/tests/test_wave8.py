"""Tests for wave 8: data lineage, service catalog, adaptive retry,
rotation scheduler, and capacity planner.
"""
from __future__ import annotations

import time

import pytest

from skeleton.data.lineage import DataLineage
from skeleton.intelligence.capacity_planner import CapacityPlanner
from skeleton.mesh.service_catalog import ServiceCatalog
from skeleton.resilience.adaptive_retry import AdaptiveRetry
from skeleton.security.rotation_scheduler import RotationScheduler


class TestDataLineage:
    def test_transform_chain(self):
        lin = DataLineage()
        lin.record_transform("raw", "clean", "dedupe", "etl")
        lin.record_transform("clean", "features", "extract", "etl")
        assert lin.upstream("features") == ["clean", "raw"]
        assert lin.downstream("raw") == ["clean", "features"]

    def test_impact_analysis(self):
        lin = DataLineage()
        lin.record_transform("events", "agg", "rollup", "analytics")
        impact = lin.impact_analysis("events")
        assert "agg" in impact["impacted_datasets"]

    def test_access_report(self):
        lin = DataLineage()
        lin.register_dataset("users", "data-team")
        lin.record_access("users", "alice", "read")
        assert len(lin.access_report("users")) == 1

    def test_orphans_detected(self):
        lin = DataLineage()
        lin.register_dataset("lonely", "team")
        assert "lonely" in lin.card()["orphans"]


class TestServiceCatalog:
    def test_register_and_lookup(self):
        cat = ServiceCatalog()
        cat.register("api", "platform", tier="tier1", oncall="#platform-oncall")
        entry = cat.get("api")
        assert entry.owner == "platform"
        assert cat.oncall_for("api") == "#platform-oncall"

    def test_by_owner(self):
        cat = ServiceCatalog()
        cat.register("a", "team-x")
        cat.register("b", "team-x")
        cat.register("c", "team-y")
        assert len(cat.by_owner("team-x")) == 2

    def test_undocumented(self):
        cat = ServiceCatalog()
        cat.register("nodocs", "team")
        cat.register("hasdocs", "team", docs="https://wiki/x")
        assert cat.undocumented() == ["nodocs"]

    def test_orphan_dependencies(self):
        cat = ServiceCatalog()
        cat.register("svc", "team", dependencies=["ghost"])
        assert cat.orphan_dependencies() == {"svc": ["ghost"]}

    def test_update(self):
        cat = ServiceCatalog()
        cat.register("svc", "team")
        assert cat.update("svc", oncall="#new-channel")
        assert cat.oncall_for("svc") == "#new-channel"


class TestAdaptiveRetry:
    def test_success_first_try(self):
        retry = AdaptiveRetry()
        result = retry.execute("api", lambda: 42)
        assert result["success"]
        assert result["attempts"] == 1

    def test_transient_retried(self):
        retry = AdaptiveRetry()
        calls = []
        def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise TimeoutError("slow")
            return "ok"
        result = retry.execute("api", flaky)
        assert result["success"]
        assert result["attempts"] == 2

    def test_permanent_fails_fast(self):
        retry = AdaptiveRetry()
        calls = []
        def bad():
            calls.append(1)
            raise ValueError("bad input")
        result = retry.execute("api", bad)
        assert not result["success"]
        assert result.get("failed_fast")
        assert len(calls) == 1

    def test_learned_permanent(self):
        retry = AdaptiveRetry()
        class WeirdError(Exception):
            pass
        retry.execute("ep", lambda: (_ for _ in ()).throw(WeirdError("x")))
        # unknown error learned as permanent; next time fails fast immediately
        result = retry.execute("ep", lambda: (_ for _ in ()).throw(WeirdError("y")))
        assert result.get("failed_fast")
        assert "WeirdError" in retry.card()["endpoints"]["ep"]["learned_permanent"]

    def test_exhaustion(self):
        retry = AdaptiveRetry()
        retry.tune("ep2", max_attempts=2)
        result = retry.execute("ep2", lambda: (_ for _ in ()).throw(TimeoutError("t")))
        assert result.get("exhausted")


class TestRotationScheduler:
    def test_due_detection(self):
        rs = RotationScheduler()
        rs.set_policy("api_key", max_age_s=10)
        rs.assign_class("key-1", "api_key")
        created = {"key-1": time.time_ns() - int(20e9)}
        due = rs.due_for_rotation(created)
        assert len(due) == 1
        assert due[0]["secret"] == "key-1"

    def test_not_due_when_fresh(self):
        rs = RotationScheduler()
        rs.set_policy("token", max_age_s=3600)
        rs.assign_class("tok", "token")
        due = rs.due_for_rotation({"tok": time.time_ns()})
        assert due == []

    def test_rotate_records_history(self):
        rs = RotationScheduler()
        rs.set_policy("api_key", 10)
        rs.assign_class("k", "api_key")
        result = rs.rotate("k")
        assert result["rotated"] == "k"
        assert rs.last_rotation("k") is not None

    def test_overlap_window(self):
        rs = RotationScheduler()
        rs.set_policy("token", 10, overlap_s=60)
        rs.assign_class("t", "token")
        rs.rotate("t")
        assert rs.overlap_active("t")

    def test_run_scheduled_only_auto(self):
        rs = RotationScheduler()
        rs.set_policy("manual", 1, auto_rotate=False)
        rs.assign_class("m", "manual")
        rotated = rs.run_scheduled({"m": time.time_ns() - int(10e9)})
        assert rotated == []


class TestCapacityPlanner:
    def test_headroom_and_utilization(self):
        cp = CapacityPlanner()
        cp.define_pool("workers", 100, "workers")
        cp.record_usage("workers", 40)
        card = cp.card()
        assert card["pools"]["workers"]["headroom"] == 60.0

    def test_saturation_estimate(self):
        cp = CapacityPlanner()
        cp.define_pool("disk", 100, "gb")
        cp.record_usage("disk", 50)
        cp.record_usage("disk", 60)
        est = cp.saturation_estimate("disk")
        assert est["saturates"]
        assert est["steps_until_full"] == 4.0

    def test_scale_up_recommendation(self):
        cp = CapacityPlanner()
        cp.define_pool("cache", 100, "entries")
        cp.record_usage("cache", 90)
        recs = cp.analyze()
        assert recs[0]["action"] == "scale_up"
        assert recs[0]["suggested_capacity"] == 150.0

    def test_scale_down_recommendation(self):
        cp = CapacityPlanner()
        cp.define_pool("pool", 100, "units")
        for _ in range(12):
            cp.record_usage("pool", 10)
        recs = cp.analyze()
        assert any(r["action"] == "scale_down" for r in recs)

    def test_no_saturation_flat(self):
        cp = CapacityPlanner()
        cp.define_pool("q", 100, "slots")
        cp.record_usage("q", 50)
        cp.record_usage("q", 50)
        assert not cp.saturation_estimate("q")["saturates"]
