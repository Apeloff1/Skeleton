"""Tests for wave 12: request hedging, snapshot replication, API
versioning, fault injection harness, and compliance reporter.
"""
from __future__ import annotations

import time

import pytest

from skeleton.api.versioning import APIVersioning
from skeleton.mesh.request_hedging import RequestHedger
from skeleton.reliability.fault_injection_harness import FaultInjectionHarness
from skeleton.reliability.snapshot_replication import SnapshotReplicator
from skeleton.security.compliance_reporter import ComplianceReporter


class TestRequestHedging:
    def test_fast_request_no_hedge(self):
        h = RequestHedger()
        result = h.execute("api", lambda: "ok", backup=lambda: "hedge")
        assert not result["hedged"]

    def test_p95_tracking(self):
        h = RequestHedger()
        for i in range(100):
            h.record_latency("api", float(i))
        assert h.hedge_delay_ms("api") >= 94.0

    def test_budget_enforced(self):
        h = RequestHedger()
        stat = h._stat("api")
        stat.requests = 100
        stat.hedged = 10
        assert not h.budget_allows("api")

    def test_cold_start_grace(self):
        h = RequestHedger()
        assert h.budget_allows("new-svc")


class TestSnapshotReplication:
    def test_publish_and_sync(self):
        rep = SnapshotReplicator()
        rep.add_replica("eu-west")
        rep.publish({"key": "v1"})
        rep.publish({"key": "v2"})
        result = rep.sync("eu-west")
        assert result["applied"] == 2
        assert result["lag"] == 0

    def test_lag_tracking(self):
        rep = SnapshotReplicator()
        rep.add_replica("us-east")
        for _ in range(5):
            rep.publish({"n": 1})
        card = rep.card()
        assert card["replicas"]["us-east"]["lag"] == 5

    def test_consistency_check(self):
        rep = SnapshotReplicator()
        rep.add_replica("r1")
        rep.publish({"x": 1})
        rep.sync("r1")
        check = rep.verify_consistency("r1")
        assert check["consistent"]
        rep.publish({"x": 2})
        assert not rep.verify_consistency("r1")["up_to_date"]

    def test_failover_readiness(self):
        rep = SnapshotReplicator(max_lag=3)
        rep.add_replica("dr")
        for _ in range(2):
            rep.publish({"k": "v"})
        rep.sync("dr")
        assert rep.failover_ready("dr")
        for _ in range(10):
            rep.publish({"k": "v"})
        assert not rep.failover_ready("dr")


class TestAPIVersioning:
    def test_serve_latest_by_default(self):
        av = APIVersioning()
        av.register("/users", "v1", lambda p: {"v": 1})
        av.register("/users", "v2", lambda p: {"v": 2})
        resp = av.serve("/users", {})
        assert resp["version"] == "v2"

    def test_explicit_version(self):
        av = APIVersioning()
        av.register("/users", "v1", lambda p: {"v": 1})
        av.register("/users", "v2", lambda p: {"v": 2})
        resp = av.serve("/users", {}, requested="v1")
        assert resp["version"] == "v1"

    def test_deprecation_warning(self):
        av = APIVersioning()
        av.register("/x", "v1", lambda p: {})
        av.deprecate("/x", "v1", sunset_days=30)
        resp = av.serve("/x", {}, requested="v1")
        assert "warning" in resp
        assert "deprecated" in resp["warning"]

    def test_sunset_blocks(self):
        av = APIVersioning()
        av.register("/old", "v1", lambda p: {})
        av.deprecate("/old", "v1", sunset_days=-1)
        resp = av.serve("/old", {}, requested="v1")
        assert resp["status"] == 410

    def test_retirement_candidates(self):
        av = APIVersioning()
        av.register("/r", "v1", lambda p: {})
        av.register("/r", "v2", lambda p: {})
        av.deprecate("/r", "v1")
        for _ in range(100):
            av.serve("/r", {}, requested="v2")
        av.serve("/r", {}, requested="v1")
        assert "/r@v1" in av.retirement_candidates()


class TestFaultInjectionHarness:
    def test_passing_scenario(self):
        harness = FaultInjectionHarness()
        harness.scenario("db-down", "dependency_down", "db", setup=lambda: {"circuit_open": True})
        harness.assert_that("db-down", "circuit opens", lambda ctx: ctx["circuit_open"])
        result = harness.run("db-down")
        assert result.passed

    def test_failing_assertion(self):
        harness = FaultInjectionHarness()
        harness.scenario("slow-dep", "slow_dependency", "cache")
        harness.assert_that("slow-dep", "shedder engages", lambda ctx: False)
        result = harness.run("slow-dep")
        assert not result.passed

    def test_assertion_exception_caught(self):
        harness = FaultInjectionHarness()
        harness.scenario("crash", "cascade", "api")
        harness.assert_that("crash", "check", lambda ctx: 1 / 0)
        result = harness.run("crash")
        assert not result.passed
        assert "division" in result.assertions[0]["detail"]

    def test_verification_score(self):
        harness = FaultInjectionHarness()
        harness.scenario("s1", "x", "t")
        harness.assert_that("s1", "pass", lambda c: True)
        harness.assert_that("s1", "fail", lambda c: False)
        harness.run("s1")
        assert harness.verification_score() == 0.5


class TestComplianceReporter:
    def test_evaluate_controls(self):
        cr = ComplianceReporter()
        cr.add_control("AC-1", "SOC2-lite", "RBAC defined", lambda: True)
        cr.add_control("SC-1", "SOC2-lite", "Encryption on", lambda: False)
        report = cr.evaluate()
        assert report["overall_coverage"] == 0.5
        assert report["frameworks"]["SOC2-lite"]["satisfied"] == 1

    def test_gaps_listed(self):
        cr = ComplianceReporter()
        cr.add_control("AU-1", "SOC2-lite", "Audit log", lambda: False)
        cr.evaluate()
        gaps = cr.gaps("SOC2-lite")
        assert gaps[0]["control"] == "AU-1"

    def test_framework_separation(self):
        cr = ComplianceReporter()
        cr.add_control("A", "SOC2-lite", "a", lambda: True)
        cr.add_control("B", "ISO-lite", "b", lambda: True)
        report = cr.evaluate()
        assert "SOC2-lite" in report["frameworks"]
        assert "ISO-lite" in report["frameworks"]

    def test_failing_evidence_fn(self):
        cr = ComplianceReporter()
        cr.add_control("X", "SOC2-lite", "broken check", lambda: 1 / 0)
        report = cr.evaluate()
        assert report["frameworks"]["SOC2-lite"]["satisfied"] == 0
