"""Tests for wave 13: audit analytics, config templates, connection
pool, graceful shutdown, and burn rate alerter.
"""
from __future__ import annotations

import time

import pytest

from skeleton.core.graceful_shutdown import GracefulShutdown
from skeleton.mesh.connection_pool import ConnectionPool
from skeleton.observability.audit_analytics import AuditAnalytics
from skeleton.observability.burn_rate_alerter import BurnRateAlerter
from skeleton.observability.sla_tracker import SLATracker
from skeleton.organism.config_templates import ConfigTemplates


class TestAuditAnalytics:
    def test_actor_activity(self):
        aa = AuditAnalytics()
        aa.ingest("alice", "deploy", "api")
        aa.ingest("alice", "rollback", "api")
        aa.ingest("bob", "deploy", "db")
        activity = aa.actor_activity()
        assert activity["alice"] == 2

    def test_bursts_detected(self):
        aa = AuditAnalytics(burst_window_s=60, burst_threshold=5)
        now = time.time_ns()
        for i in range(10):
            aa.ingest("noisy", "action", "res", timestamp_ns=now + i * 1_000_000_000)
        bursts = aa.bursts()
        assert len(bursts) == 1
        assert bursts[0]["actor"] == "noisy"

    def test_no_burst_when_spread(self):
        aa = AuditAnalytics(burst_window_s=10, burst_threshold=5)
        now = time.time_ns()
        for i in range(10):
            aa.ingest("calm", "action", "res", timestamp_ns=now + i * 60_000_000_000)
        assert aa.bursts() == []

    def test_self_grant_detected(self):
        aa = AuditAnalytics()
        aa.ingest("mallory", "grant", "rbac", details={"role": "admin", "granted_by": "mallory"})
        chains = aa.escalation_chains()
        assert len(chains) == 1
        assert chains[0]["self_grant"]

    def test_digest(self):
        aa = AuditAnalytics()
        aa.ingest("a", "deploy", "api")
        digest = aa.digest()
        assert digest["records"] == 1
        assert "deploy" in digest["top_actions"]


class TestConfigTemplates:
    def test_define_and_instantiate(self):
        ct = ConfigTemplates()
        ct.define("small", {"workers": "${count}", "cache": 100}, parameters={"count": 2})
        resolved = ct.instantiate("small")
        assert resolved["workers"] == 2
        assert resolved["cache"] == 100

    def test_param_override(self):
        ct = ConfigTemplates()
        ct.define("t", {"w": "${n}"}, parameters={"n": 1})
        resolved = ct.instantiate("t", params={"n": 9})
        assert resolved["w"] == 9

    def test_missing_param_raises(self):
        ct = ConfigTemplates()
        ct.define("t", {"w": "${needed}"})
        with pytest.raises(KeyError):
            ct.instantiate("t")

    def test_nested_resolution(self):
        ct = ConfigTemplates()
        ct.define("t", {"db": {"host": "${host}", "port": 5432}}, parameters={"host": "localhost"})
        resolved = ct.instantiate("t")
        assert resolved["db"]["host"] == "localhost"

    def test_versioning(self):
        ct = ConfigTemplates()
        ct.define("t", {"v": 1})
        ct.define("t", {"v": 2})
        assert ct.latest("t").version == 2
        assert ct.instantiate("t", version=1) == {"v": 1}


class TestConnectionPool:
    def test_checkout_checkin(self):
        pool = ConnectionPool()
        result = pool.checkout("db:5432")
        assert result["acquired"]
        assert pool.checkin("db:5432", result["conn_id"])

    def test_reuse(self):
        pool = ConnectionPool()
        r1 = pool.checkout("api:8080")
        pool.checkin("api:8080", r1["conn_id"])
        r2 = pool.checkout("api:8080")
        assert r2["reused"]

    def test_exhaustion(self):
        pool = ConnectionPool()
        conns = []
        for _ in range(10):
            conns.append(pool.checkout("svc"))
        result = pool.checkout("svc")
        assert not result["acquired"]

    def test_broken_not_reused(self):
        pool = ConnectionPool()
        r = pool.checkout("svc")
        pool.checkin("svc", r["conn_id"], broken=True)
        stats = pool.stats("svc")
        assert stats["available"] == 0


class TestGracefulShutdown:
    def test_phased_execution(self):
        gs = GracefulShutdown()
        order = []
        gs.register("intake", "stop_intake", lambda: order.append("intake") or True)
        gs.register("drain", "drain_inflight", lambda: order.append("drain") or True)
        gs.register("term", "terminate", lambda: order.append("term") or True)
        result = gs.execute()
        assert result["completed"]
        assert order == ["intake", "drain", "term"]

    def test_stops_accepting(self):
        gs = GracefulShutdown()
        assert gs.is_accepting()
        gs.initiate()
        assert not gs.is_accepting()

    def test_hook_failure_visible(self):
        gs = GracefulShutdown()
        gs.register("bad", "drain_inflight", lambda: (_ for _ in ()).throw(RuntimeError("stuck")))
        result = gs.execute()
        assert not result["phases"]["drain_inflight"]["ok"]

    def test_unknown_phase_rejected(self):
        gs = GracefulShutdown()
        with pytest.raises(ValueError):
            gs.register("x", "invalid_phase", lambda: True)

    def test_status_pending(self):
        gs = GracefulShutdown()
        gs.register("h", "terminate", lambda: True)
        assert "h" in gs.status()["pending"]


class TestBurnRateAlerter:
    def _sla_with_burn(self, rate: float):
        sla = SLATracker()
        sla.register("api", "availability", 0.999)
        # burn_rate > threshold requires bad fraction > allowed * rate
        for _ in range(100):
            sla.record("api", "availability", 1.0, good=True)
        for _ in range(int(100 * rate * 0.001)):
            sla.record("api", "availability", 0.0, good=False)
        return sla

    def test_no_alert_healthy(self):
        sla = SLATracker()
        sla.register("api", "availability", 0.999)
        for _ in range(100):
            sla.record("api", "availability", 1.0, good=True)
        bra = BurnRateAlerter(sla_tracker=sla)
        assert bra.evaluate("api", "availability") == []

    def test_fast_burn_fires(self):
        sla = SLATracker()
        sla.register("api", "availability", 0.999)
        for _ in range(100):
            sla.record("api", "availability", 0.0, good=False)
        bra = BurnRateAlerter(sla_tracker=sla)
        fired = bra.evaluate("api", "availability")
        assert any(a["kind"] == "fast_burn" for a in fired)

    def test_no_duplicate_alerts(self):
        sla = SLATracker()
        sla.register("api", "availability", 0.999)
        for _ in range(100):
            sla.record("api", "availability", 0.0, good=False)
        bra = BurnRateAlerter(sla_tracker=sla)
        first = bra.evaluate("api", "availability")
        second = bra.evaluate("api", "availability")
        assert len(second) == 0

    def test_silence(self):
        sla = SLATracker()
        sla.register("api", "availability", 0.999)
        for _ in range(100):
            sla.record("api", "availability", 0.0, good=False)
        bra = BurnRateAlerter(sla_tracker=sla)
        bra.silence("api.availability", 3600)
        assert bra.evaluate("api", "availability") == []

    def test_acknowledge(self):
        sla = SLATracker()
        sla.register("api", "availability", 0.999)
        for _ in range(100):
            sla.record("api", "availability", 0.0, good=False)
        bra = BurnRateAlerter(sla_tracker=sla)
        bra.evaluate("api", "availability")
        assert bra.acknowledge("api.availability", "fast_burn")
