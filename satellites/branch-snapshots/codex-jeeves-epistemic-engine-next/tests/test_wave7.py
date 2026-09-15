"""Tests for wave 7: incident manager, quota enforcer, feature store,
release notes generator, and synthetic monitor.
"""
from __future__ import annotations

import time

import pytest

from skeleton.cortex.incident_manager import IncidentManager
from skeleton.deployment.release_notes import ReleaseNotesGenerator
from skeleton.intelligence.feature_store import FeatureStore
from skeleton.reliability.synthetic_monitor import SyntheticMonitor
from skeleton.security.quota_enforcer import QuotaEnforcer


class TestIncidentManager:
    def test_full_lifecycle(self):
        im = IncidentManager()
        inc = im.declare("DB down", severity="sev1", alert_ids=["a1"])
        assert inc.state == "triggered"
        assert im.acknowledge(inc.incident_id, "oncall")
        assert im.assign_commander(inc.incident_id, "oncall")
        assert im.mitigate(inc.incident_id, "oncall", "failed over")
        assert im.resolve(inc.incident_id, "oncall", "verified stable")
        result = im.complete_postmortem(inc.incident_id, "summary", "root cause", "actions")
        assert result["completed"]
        assert im._incidents[inc.incident_id].state == "postmortem"

    def test_no_backward_transition(self):
        im = IncidentManager()
        inc = im.declare("x")
        im.acknowledge(inc.incident_id, "a")
        assert not im._transition(inc.incident_id, "triggered", "a")

    def test_postmortem_requires_resolved(self):
        im = IncidentManager()
        inc = im.declare("y")
        result = im.complete_postmortem(inc.incident_id, "s", "r", "a")
        assert not result["completed"]

    def test_metrics(self):
        im = IncidentManager()
        inc = im.declare("z")
        im.acknowledge(inc.incident_id, "a")
        im.resolve(inc.incident_id, "a")
        metrics = im.metrics()
        assert metrics["total"] == 1
        assert metrics["open"] == 0


class TestQuotaEnforcer:
    def test_consume_within_limit(self):
        qe = QuotaEnforcer()
        qe.define("api-req", "requests", 100)
        result = qe.consume("api-req", 50, actor="alice")
        assert result["allowed"]
        assert result["utilization"] == 0.5

    def test_hard_limit_blocks(self):
        qe = QuotaEnforcer()
        qe.define("compute", "seconds", 10)
        qe.consume("compute", 9)
        result = qe.consume("compute", 5)
        assert not result["allowed"]
        assert "hard limit" in result["reason"]

    def test_soft_limit_warns(self):
        qe = QuotaEnforcer()
        qe.define("storage", "bytes", 100, soft_fraction=0.5)
        result = qe.consume("storage", 60)
        assert result["allowed"]
        assert "warning" in result

    def test_no_quota_allows(self):
        qe = QuotaEnforcer()
        assert qe.consume("undefined-key")["allowed"]

    def test_period_reset(self):
        qe = QuotaEnforcer()
        q = qe.define("q", "r", 10, period_s=0.01)
        qe.consume("q", 10)
        time.sleep(0.02)
        assert qe.consume("q", 5)["allowed"]

    def test_violations_tracked(self):
        qe = QuotaEnforcer()
        qe.define("v", "r", 1)
        qe.consume("v", 5)
        assert qe.card()["violations"] == 1


class TestFeatureStore:
    def test_register_and_online(self):
        fs = FeatureStore()
        fs.register("clicks", "user", ttl_s=3600)
        fs.write("clicks", "u1", 42)
        assert fs.online("clicks", "u1") == 42

    def test_unregistered_rejected(self):
        fs = FeatureStore()
        with pytest.raises(KeyError):
            fs.write("ghost", "u1", 1)

    def test_stale_returns_none(self):
        fs = FeatureStore()
        fs.register("f", "user", ttl_s=0.01)
        fs.write("f", "u1", 7)
        time.sleep(0.02)
        assert fs.online("f", "u1") is None

    def test_point_in_time_no_leakage(self):
        fs = FeatureStore()
        fs.register("score", "user")
        fs.write("score", "u1", 10, timestamp_ns=100)
        fs.write("score", "u1", 99, timestamp_ns=200)
        assert fs.point_in_time("score", "u1", 150) == 10
        assert fs.point_in_time("score", "u1", 250) == 99

    def test_training_set(self):
        fs = FeatureStore()
        fs.register("a", "user")
        fs.register("b", "user")
        fs.write("a", "u1", 1, timestamp_ns=100)
        fs.write("b", "u1", 2, timestamp_ns=100)
        rows = fs.training_set(["a", "b"], ["u1"], as_of_ns=150)
        assert rows[0]["a"] == 1 and rows[0]["b"] == 2

    def test_versioning(self):
        fs = FeatureStore()
        fs.register("f", "user")
        fd = fs.register("f", "user")
        assert fd.version == 2


class TestReleaseNotes:
    def test_cut_and_render(self):
        rng = ReleaseNotesGenerator()
        rng.add("api", "feature", "Added gateway")
        rng.add("db", "fix", "Fixed connection leak")
        rng.cut_release("1.2.0")
        notes = rng.render("1.2.0")
        assert "# Release 1.2.0" in notes
        assert "Added gateway" in notes

    def test_breaking_section(self):
        rng = ReleaseNotesGenerator()
        rng.add("api", "breaking", "Removed legacy endpoint")
        rng.cut_release("2.0.0")
        assert rng.requires_migration_notes("2.0.0")
        assert "Breaking Changes" in rng.render("2.0.0")

    def test_publish(self):
        rng = ReleaseNotesGenerator()
        rng.add("x", "chore", "cleanup")
        rng.cut_release("0.1")
        result = rng.publish("0.1")
        assert result["published"]

    def test_pending_cleared_on_cut(self):
        rng = ReleaseNotesGenerator()
        rng.add("x", "fix", "f")
        rng.cut_release("1")
        assert rng.card()["pending_entries"] == 0


class TestSyntheticMonitor:
    def test_successful_journey(self):
        sm = SyntheticMonitor()
        sm.register("login-flow", [("load", lambda: None), ("auth", lambda: None)])
        probe = sm.run("login-flow")
        assert probe.ok
        assert sm.uptime("login-flow") == 1.0

    def test_fail_fast(self):
        sm = SyntheticMonitor()
        calls = []
        def step2():
            calls.append(1)
        sm.register("j", [("fail", lambda: (_ for _ in ()).throw(ValueError("x"))), ("never", step2)])
        probe = sm.run("j")
        assert not probe.ok
        assert calls == []

    def test_consecutive_failures_alert(self):
        sm = SyntheticMonitor(alert_after_failures=2)
        sm.register("bad", [("x", lambda: (_ for _ in ()).throw(RuntimeError("e")))])
        sm.run("bad")
        assert sm.alerting_journeys() == []
        sm.run("bad")
        assert "bad" in sm.alerting_journeys()

    def test_recovery_resets(self):
        sm = SyntheticMonitor(alert_after_failures=2)
        state = {"fail": True}
        def step():
            if state["fail"]:
                raise RuntimeError("x")
        sm.register("flaky", [("s", step)])
        sm.run("flaky")
        state["fail"] = False
        sm.run("flaky")
        assert sm._journeys["flaky"].consecutive_failures == 0
