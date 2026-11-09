"""Tests for wave 9: config diff, job orchestrator, metrics registry,
escalation policy, and access review.
"""
from __future__ import annotations

import time

import pytest

from skeleton.core.job_orchestrator import JobOrchestrator
from skeleton.cortex.escalation import EscalationPolicy
from skeleton.observability.metrics_registry import MetricsRegistry
from skeleton.organism.config_diff import ConfigDiff
from skeleton.security.access_review import AccessReview
from skeleton.security.rbac import RBACRegistry
import tempfile
from pathlib import Path


class TestConfigDiff:
    def test_diff_modified(self):
        cd = ConfigDiff()
        result = cd.diff({"a": 1}, {"a": 2})
        assert result["total"] == 1
        assert result["changes"][0]["kind"] == "modified"

    def test_diff_added_removed(self):
        cd = ConfigDiff()
        result = cd.diff({"a": 1, "b": 2}, {"a": 1, "c": 3})
        kinds = {c["path"]: c["kind"] for c in result["changes"]}
        assert kinds["b"] == "removed"
        assert kinds["c"] == "added"

    def test_sensitive_keys_critical(self):
        cd = ConfigDiff()
        result = cd.diff({"db.password": "x"}, {"db.password": "y"})
        assert result["max_risk"] == "critical"
        assert result["requires_review"]
        # values must be redacted
        assert result["changes"][0]["old"] is None

    def test_removal_is_high_risk(self):
        cd = ConfigDiff()
        result = cd.diff({"feature": {"x": 1}}, {})
        assert result["max_risk"] == "high"

    def test_snapshot_and_drift(self):
        cd = ConfigDiff()
        snap = cd.snapshot({"a": 1})
        result = cd.drift(snap.snapshot_id, {"a": 2})
        assert result["drifted"]

    def test_no_drift(self):
        cd = ConfigDiff()
        snap = cd.snapshot({"a": 1})
        assert not cd.drift(snap.snapshot_id, {"a": 1})["drifted"]


class TestJobOrchestrator:
    def test_full_run(self):
        jo = JobOrchestrator()
        done = []
        state = jo.submit("backfill", iter([1, 2, 3]), lambda c, ck: done.append(c))
        result = jo.run(state.job_id)
        assert result["status"] == "completed"
        assert done == [1, 2, 3]

    def test_partial_run_with_max_chunks(self):
        jo = JobOrchestrator()
        state = jo.submit("j", iter([1, 2, 3, 4]), lambda c, ck: None)
        jo.run(state.job_id, max_chunks=2)
        assert self._progress(jo, state.job_id) == 0.5

    def _progress(self, jo, job_id):
        return jo._jobs[job_id].progress()

    def test_failure_and_retry(self):
        jo = JobOrchestrator()
        attempts = []
        def process(chunk, ck):
            attempts.append(chunk)
            if chunk == 2 and len(attempts) < 3:
                raise RuntimeError("bad chunk")
        state = jo.submit("j", iter([1, 2, 3]), process)
        result = jo.run(state.job_id)
        assert result["status"] == "failed"
        resumed = jo.retry_failed(state.job_id)
        assert resumed["status"] == "completed"
        assert self._progress(jo, state.job_id) == 1.0

    def test_pause_resume(self):
        jo = JobOrchestrator()
        state = jo.submit("j", iter(range(10)), lambda c, ck: None)
        jo.run(state.job_id, max_chunks=3)
        jo._jobs[state.job_id].status = "running"
        assert jo.pause(state.job_id)
        result = jo.resume(state.job_id)
        assert result["status"] == "completed"


class TestMetricsRegistry:
    def test_counter_accumulates(self):
        reg = MetricsRegistry()
        reg.counter("requests", 5)
        reg.counter("requests", 3)
        assert reg.get_counter("requests") == 8.0

    def test_label_isolation(self):
        reg = MetricsRegistry()
        reg.counter("hits", labels={"path": "/a"})
        reg.counter("hits", 2, labels={"path": "/b"})
        assert reg.get_counter("hits", {"path": "/a"}) == 1.0
        assert reg.get_counter("hits", {"path": "/b"}) == 2.0

    def test_histogram_stats(self):
        reg = MetricsRegistry()
        for i in range(100):
            reg.observe("latency", float(i))
        stats = reg.histogram_stats("latency")
        assert stats["count"] == 100
        assert stats["p50"] == 50.0

    def test_timer_context(self):
        reg = MetricsRegistry()
        with reg.timer("op"):
            pass
        assert reg.histogram_stats("op")["count"] == 1

    def test_threshold_hook(self):
        reg = MetricsRegistry()
        fired = []
        reg.set_threshold("errors", 5)
        reg.on_threshold(lambda name, value, thr: fired.append((name, value)))
        reg.counter("errors", 10)
        assert fired == [("errors", 10.0)]


class TestEscalationPolicy:
    def test_trigger_pages_level_zero(self):
        paged = []
        ep = EscalationPolicy(notify=lambda t, a, m: paged.append(t))
        ep.define("std", [{"targets": ["l1"], "timeout_s": 60}, {"targets": ["l2"], "timeout_s": 60}])
        ep.trigger("alert-1", "std")
        assert paged == ["l1"]

    def test_escalates_on_timeout(self):
        paged = []
        ep = EscalationPolicy(notify=lambda t, a, m: paged.append(t))
        ep.define("std", [{"targets": ["l1"], "timeout_s": 0.01}, {"targets": ["l2"], "timeout_s": 60}])
        ep.trigger("alert-1", "std")
        time.sleep(0.02)
        advanced = ep.tick()
        assert advanced[0]["new_level"] == 1
        assert "l2" in paged

    def test_ack_stops_escalation(self):
        ep = EscalationPolicy()
        ep.define("std", [{"targets": ["l1"], "timeout_s": 0.01}, {"targets": ["l2"]}])
        ep.trigger("a", "std")
        assert ep.acknowledge("a", "oncall")
        time.sleep(0.02)
        assert ep.tick() == []

    def test_expires_after_last_level(self):
        ep = EscalationPolicy()
        ep.define("std", [{"targets": ["l1"], "timeout_s": 0.01}])
        ep.trigger("a", "std")
        time.sleep(0.02)
        advanced = ep.tick()
        assert advanced[0]["status"] == "expired"


class TestAccessReview:
    def test_campaign_flow(self):
        with tempfile.TemporaryDirectory() as td:
            rbac = RBACRegistry(root=Path(td))
            rbac.grant("alice", "viewer")
            ar = AccessReview(rbac=rbac)
            camp = ar.start_campaign({"alice": ["viewer"]})
            assert ar.decide(camp.campaign_id, "alice", "viewer", "certified", "manager")
            report = ar.report(camp.campaign_id)
            assert report["certified"] == 1

    def test_revoke_flows_to_rbac(self):
        with tempfile.TemporaryDirectory() as td:
            rbac = RBACRegistry(root=Path(td))
            rbac.grant("bob", "operator")
            ar = AccessReview(rbac=rbac)
            camp = ar.start_campaign({"bob": ["operator"]})
            ar.decide(camp.campaign_id, "bob", "operator", "revoked", "manager")
            assert not rbac.check("bob", "repair.trigger")

    def test_stale_detection(self):
        ar = AccessReview(stale_days=1)
        camp = ar.start_campaign({"carol": ["viewer"]})
        stale = ar.stale_grants(camp.campaign_id)
        assert stale[0]["never_used"]

    def test_close_report(self):
        ar = AccessReview()
        camp = ar.start_campaign({"d": ["viewer"]})
        ar.decide(camp.campaign_id, "d", "viewer", "certified", "m")
        report = ar.close(camp.campaign_id)
        assert report["closed"]
        assert report["completion"] == 1.0
