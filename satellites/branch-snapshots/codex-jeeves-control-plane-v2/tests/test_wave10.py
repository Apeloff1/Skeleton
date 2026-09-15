"""Tests for wave 10: policy engine, error taxonomy, throughput
controller, environment manager, and on-call rotation.
"""
from __future__ import annotations

import time

import pytest

from skeleton.cortex.oncall_rotation import OnCallRotation
from skeleton.deployment.environment_manager import EnvironmentManager
from skeleton.intelligence.error_taxonomy import ErrorTaxonomy
from skeleton.mesh.throughput_controller import ThroughputController
from skeleton.security.policy_engine import PolicyEngine


class TestPolicyEngine:
    def test_deny_rule(self):
        pe = PolicyEngine()
        pe.define("deploy")
        pe.add_rule("deploy", "no-friday", lambda ctx: ctx.get("day") == "friday", effect="deny", reason="no friday deploys")
        decision = pe.evaluate("deploy", {"day": "friday"})
        assert not decision.allowed
        assert decision.matched_rule == "no-friday"

    def test_default_allow(self):
        pe = PolicyEngine()
        pe.define("deploy")
        pe.add_rule("deploy", "no-friday", lambda ctx: ctx.get("day") == "friday", effect="deny")
        assert pe.evaluate("deploy", {"day": "monday"}).allowed

    def test_all_combinator(self):
        pe = PolicyEngine()
        pe.define("access", combinator="all", default="deny")
        pe.add_rule("access", "r1", lambda c: c.get("authed"), effect="allow")
        pe.add_rule("access", "r2", lambda c: c.get("mfa"), effect="allow")
        assert pe.evaluate("access", {"authed": True, "mfa": True}).allowed
        assert not pe.evaluate("access", {"authed": True}).allowed

    def test_deny_rate(self):
        pe = PolicyEngine()
        pe.define("p")
        pe.add_rule("p", "block", lambda c: c.get("bad"), effect="deny")
        pe.evaluate("p", {"bad": True})
        pe.evaluate("p", {"bad": False})
        assert pe.deny_rate("p") == 0.5

    def test_decision_trace(self):
        pe = PolicyEngine()
        pe.define("x")
        pe.add_rule("x", "rule1", lambda c: True, effect="deny", reason="always")
        d = pe.evaluate("x", {})
        assert d.reason == "always"


class TestErrorTaxonomy:
    def test_classification(self):
        et = ErrorTaxonomy()
        assert et.classify(TimeoutError("x")) == "timeout"
        assert et.classify(PermissionError("x")) == "permission"
        assert et.classify(ValueError("invalid")) == "validation"

    def test_fingerprint_aggregation(self):
        et = ErrorTaxonomy()
        et.record("api", ValueError("bad id 123"))
        et.record("api", ValueError("bad id 456"))
        # same fingerprint — numbers stripped
        assert len(et._occurrences) == 1
        assert list(et._occurrences.values())[0].count == 2

    def test_top_errors(self):
        et = ErrorTaxonomy()
        for _ in range(5):
            et.record("db", TimeoutError("t"))
        et.record("api", ValueError("v"))
        top = et.top_errors(2)
        assert top[0]["count"] == 5
        assert top[0]["retryable"]

    def test_novel_detection(self):
        et = ErrorTaxonomy(novelty_window_s=60)
        et.record("svc", RuntimeError("new problem"))
        assert len(et.novel_errors()) == 1

    def test_rollup(self):
        et = ErrorTaxonomy()
        et.record("a", TimeoutError("t"))
        et.record("b", TimeoutError("t2"))
        et.record("c", ValueError("v"))
        assert et.category_rollup()["timeout"] == 2


class TestThroughputController:
    def test_acquire_release(self):
        tc = ThroughputController()
        assert tc.acquire("api")
        tc.release("api", 50.0)
        assert tc.lane("api").inflight == 0

    def test_limit_grows_on_success(self):
        tc = ThroughputController()
        lane = tc.lane("api")
        initial = lane.limit
        tc.acquire("api")
        tc.release("api", 10.0)
        assert lane.limit > initial

    def test_limit_halves_on_error(self):
        tc = ThroughputController()
        lane = tc.lane("api")
        initial = lane.limit
        tc.acquire("api")
        tc.release("api", 10.0, error=True)
        assert lane.limit == initial * 0.5

    def test_limit_halves_on_latency_spike(self):
        tc = ThroughputController()
        lane = tc.lane("api", target_latency_ms=100)
        initial = lane.limit
        tc.acquire("api")
        tc.release("api", 500.0)
        assert lane.limit < initial

    def test_rejection_at_limit(self):
        tc = ThroughputController()
        lane = tc.lane("api")
        lane.limit = 2
        tc.acquire("api")
        tc.acquire("api")
        assert not tc.acquire("api")


class TestEnvironmentManager:
    def _setup(self):
        em = EnvironmentManager()
        em.define("dev", 0)
        em.define("stage", 1, gate_checks=["tests", "smoke"])
        em.define("prod", 2)
        return em

    def test_full_promotion_path(self):
        em = self._setup()
        em.deploy("dev", "1.0")
        em.promote("dev", "stage")
        em.pass_gate("stage", "tests")
        em.pass_gate("stage", "smoke")
        result = em.promote("stage", "prod")
        assert result["promoted"]
        assert em._envs["prod"].deployed_version == "1.0"

    def test_gate_blocks_promotion(self):
        em = self._setup()
        em.deploy("dev", "1.0")
        em.promote("dev", "stage")
        result = em.promote("stage", "prod")
        assert not result["promoted"]
        assert "gates not passed" in result["reason"]

    def test_skip_stage_blocked(self):
        em = self._setup()
        em.deploy("dev", "1.0")
        result = em.promote("dev", "prod")
        assert not result["promoted"]

    def test_locked_env(self):
        em = self._setup()
        em.lock("stage")
        em.deploy("dev", "1.0")
        result = em.promote("dev", "stage")
        assert not result["promoted"]

    def test_config_overlay(self):
        em = self._setup()
        em.define("prod-eu", 2, config_overlay={"region": "eu"})
        merged = em.resolved_config("prod-eu", {"region": "us", "debug": False})
        assert merged["region"] == "eu"
        assert merged["debug"] is False


class TestOnCallRotation:
    def test_rotation_cycles(self):
        oc = OnCallRotation()
        anchor = time.time_ns()
        oc.define("primary", ["a", "b", "c"], shift_s=60, anchor_ns=anchor)
        assert oc.who_is_oncall("primary", at_ns=anchor) == "a"
        assert oc.who_is_oncall("primary", at_ns=anchor + int(60e9)) == "b"
        assert oc.who_is_oncall("primary", at_ns=anchor + int(120e9)) == "c"
        assert oc.who_is_oncall("primary", at_ns=anchor + int(180e9)) == "a"

    def test_override_wins(self):
        oc = OnCallRotation()
        anchor = time.time_ns()
        oc.define("primary", ["a", "b"], shift_s=60, anchor_ns=anchor)
        oc.add_override("primary", "cover", anchor, anchor + int(30e9), "vacation")
        assert oc.who_is_oncall("primary", at_ns=anchor + int(10e9)) == "cover"
        assert oc.who_is_oncall("primary", at_ns=anchor + int(40e9)) == "a"

    def test_schedule(self):
        oc = OnCallRotation()
        oc.define("primary", ["a", "b"], shift_s=60)
        sched = oc.schedule("primary", shifts=3)
        assert len(sched) == 3
        members = [s["member"] for s in sched]
        assert len(set(members)) >= 1

    def test_member_management(self):
        oc = OnCallRotation()
        oc.define("primary", ["a"])
        assert not oc.remove_member("primary", "a")  # can't remove last
        assert oc.add_member("primary", "b")
        assert oc.remove_member("primary", "b")

    def test_handoff_recorded(self):
        oc = OnCallRotation()
        oc.define("primary", ["a"])
        record = oc.handoff("primary", notes="quiet shift")
        assert record["member"] == "a"
