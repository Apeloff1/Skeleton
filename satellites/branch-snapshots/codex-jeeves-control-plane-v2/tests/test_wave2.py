"""Tests for the security/core/reliability/data wave.

Covers RBAC, scheduler, plugin system, chaos engineering,
backup & restore, SLA tracking, log aggregation, migrations,
cache layer, and the notification center.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from skeleton.core.plugin_system import PluginManager, PluginManifest
from skeleton.core.scheduler import Scheduler
from skeleton.data.cache_layer import CacheLayer
from skeleton.data.migrations import MigrationRunner
from skeleton.intelligence.notification_center import NotificationCenter
from skeleton.observability.log_aggregator import LogAggregator
from skeleton.observability.sla_tracker import SLATracker
from skeleton.reliability.backup_restore import BackupManager
from skeleton.reliability.chaos import ChaosMonkey, FaultSpec
from skeleton.security.rbac import RBACRegistry


class TestRBAC:
    def test_default_roles(self):
        with tempfile.TemporaryDirectory() as td:
            rbac = RBACRegistry(root=Path(td))
            assert "admin" in [r["name"] for r in rbac.card()["roles"]]

    def test_grant_and_check(self):
        with tempfile.TemporaryDirectory() as td:
            rbac = RBACRegistry(root=Path(td))
            rbac.grant("alice", "operator")
            assert rbac.check("alice", "repair.trigger")
            assert not rbac.check("alice", "secrets.write")

    def test_admin_wildcard(self):
        with tempfile.TemporaryDirectory() as td:
            rbac = RBACRegistry(root=Path(td))
            rbac.grant("root", "admin")
            assert rbac.check("root", "anything.at.all")

    def test_revoke(self):
        with tempfile.TemporaryDirectory() as td:
            rbac = RBACRegistry(root=Path(td))
            rbac.grant("bob", "viewer")
            assert rbac.revoke("bob", "viewer")
            assert not rbac.check("bob", "policy.read")


class TestScheduler:
    def test_job_runs_when_due(self):
        sched = Scheduler()
        ran = []
        sched.add("j1", lambda: ran.append(1), interval_s=0.001, start_immediately=True)
        results = sched.tick()
        assert len(results) == 1
        assert ran == [1]

    def test_job_not_due(self):
        sched = Scheduler()
        sched.add("j2", lambda: None, interval_s=9999)
        assert sched.tick() == []

    def test_failure_recorded(self):
        sched = Scheduler()
        def boom():
            raise ValueError("x")
        sched.add("bad", boom, start_immediately=True)
        results = sched.tick()
        assert results[0]["ok"] is False
        assert sched.success_rate("bad") == 0.0

    def test_disable_job(self):
        sched = Scheduler()
        sched.add("off", lambda: None, start_immediately=True)
        sched.enable("off", False)
        assert sched.tick() == []


class TestPluginSystem:
    def test_load_and_dispatch(self):
        pm = PluginManager()
        pm.register(PluginManifest("hello", "1.0"), handlers={"greet": lambda: "hi"})
        assert pm.load("hello")
        assert pm.dispatch("greet") == "hi"

    def test_dependency_order(self):
        pm = PluginManager()
        order = []
        pm.register(PluginManifest("base", "1.0"), on_load=lambda c: order.append("base"))
        pm.register(PluginManifest("ext", "1.0", dependencies=["base"]), on_load=lambda c: order.append("ext"))
        pm.load("ext")
        assert order == ["base", "ext"]

    def test_failed_load_isolated(self):
        pm = PluginManager()
        def crash(ctx):
            raise RuntimeError("boom")
        pm.register(PluginManifest("bad", "1.0"), on_load=crash)
        assert not pm.load("bad")
        assert pm.card()["plugins"]["bad"]["error"] == "boom"

    def test_unload_blocked_by_dependent(self):
        pm = PluginManager()
        pm.register(PluginManifest("a", "1.0"))
        pm.register(PluginManifest("b", "1.0", dependencies=["a"]))
        pm.load("b")
        with pytest.raises(ValueError):
            pm.unload("a")


class TestChaos:
    def test_arm_and_inject(self):
        chaos = ChaosMonkey()
        chaos.arm("exp1", "api", [FaultSpec("error_rate", 1.0, probability=1.0)], duration_s=60)
        injected = chaos.maybe_inject("api")
        assert injected is not None
        assert injected["fault"] == "error_rate"

    def test_no_injection_other_subsystem(self):
        chaos = ChaosMonkey()
        chaos.arm("exp2", "api", [FaultSpec("drop", 1.0)], duration_s=60)
        assert chaos.maybe_inject("db") is None

    def test_disarm(self):
        chaos = ChaosMonkey()
        chaos.arm("exp3", "api", [FaultSpec("drop", 1.0)], duration_s=60)
        chaos.disarm("exp3")
        assert chaos.maybe_inject("api") is None

    def test_guard_raises_on_injected_error(self):
        chaos = ChaosMonkey()
        chaos.arm("exp4", "svc", [FaultSpec("error_rate", 1.0)], duration_s=60)
        with pytest.raises(RuntimeError):
            chaos.guard("svc", lambda: 1)


class TestBackupRestore:
    def test_backup_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "audit.jsonl").write_text('{"a":1}\n')
            bm = BackupManager(root=root)
            entry = bm.backup(label="first")
            assert entry["backup_id"] == "b0001"
            assert bm.verify("b0001")["valid"]

    def test_incremental_skips_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "audit.jsonl").write_text('{"a":1}\n')
            bm = BackupManager(root=root)
            bm.backup()
            entry2 = bm.backup(incremental=True)
            assert entry2["files"] == []

    def test_restore_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "audit.jsonl").write_text('{"a":1}\n')
            bm = BackupManager(root=root)
            bm.backup()
            (root / "audit.jsonl").unlink()
            plan = bm.restore("b0001", dry_run=True)
            assert plan["restored"] == ["audit.jsonl"]
            assert not (root / "audit.jsonl").exists()
            bm.restore("b0001", dry_run=False)
            assert (root / "audit.jsonl").exists()


class TestSLATracker:
    def test_compliance(self):
        sla = SLATracker()
        sla.register("api", "availability", 0.99)
        for _ in range(99):
            sla.record("api", "availability", 1.0, good=True)
        sla.record("api", "availability", 0.0, good=False)
        comp = sla.compliance("api", "availability")
        assert comp["compliance"] == 0.99
        assert not comp["breached"]

    def test_breach_detection(self):
        sla = SLATracker()
        sla.register("db", "availability", 0.999)
        for _ in range(10):
            sla.record("db", "availability", 0.0, good=False)
        assert sla.compliance("db", "availability")["breached"]

    def test_burn_rate(self):
        sla = SLATracker()
        sla.register("api", "success_rate", 0.99)
        for _ in range(10):
            sla.record("api", "success_rate", 0.0, good=False)
        assert sla.burn_rate("api", "success_rate") > 2.0


class TestLogAggregator:
    def test_log_and_tail(self):
        logs = LogAggregator()
        logs.info("api", "request served", path="/x")
        logs.error("api", "failed", code=500)
        tail = logs.tail("api", n=2)
        assert len(tail) == 2
        assert tail[-1]["level"] == "error"

    def test_min_level_filter(self):
        logs = LogAggregator()
        logs.debug("x", "noisy")
        logs.error("x", "important")
        tail = logs.tail("x", min_level="error")
        assert len(tail) == 1

    def test_search(self):
        logs = LogAggregator()
        logs.info("api", "user login succeeded")
        hits = logs.search("login")
        assert len(hits) == 1

    def test_rollup(self):
        logs = LogAggregator()
        logs.warning("a", "w")
        logs.error("a", "e")
        assert logs.rollup()["a"]["error"] == 1


class TestMigrations:
    def test_migrate_and_pending(self):
        with tempfile.TemporaryDirectory() as td:
            mr = MigrationRunner(root=Path(td))
            applied = []
            mr.register("001", "first", lambda r: applied.append("001"))
            mr.register("002", "second", lambda r: applied.append("002"))
            result = mr.migrate()
            assert result["migrated"] == ["001", "002"]
            assert applied == ["001", "002"]
            assert mr.pending() == []

    def test_no_double_apply(self):
        with tempfile.TemporaryDirectory() as td:
            mr = MigrationRunner(root=Path(td))
            mr.register("001", "x", lambda r: None)
            mr.migrate()
            assert mr.migrate()["migrated"] == []

    def test_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            mr = MigrationRunner(root=Path(td))
            state = []
            mr.register("001", "x", lambda r: state.append(1), down=lambda r: state.pop())
            mr.migrate()
            result = mr.rollback()
            assert result["rolled_back"] == ["001"]
            assert state == []


class TestCacheLayer:
    def test_set_get(self):
        cache = CacheLayer()
        cache.set("cards", "product", {"v": 1})
        assert cache.get("cards", "product") == {"v": 1}

    def test_ttl_expiry(self):
        cache = CacheLayer()
        cache.set("x", "k", 1, ttl_s=0.01)
        time.sleep(0.02)
        assert cache.get("x", "k") is None

    def test_get_or_compute(self):
        cache = CacheLayer()
        calls = []
        v1 = cache.get_or_compute("c", "k", lambda: calls.append(1) or 42)
        v2 = cache.get_or_compute("c", "k", lambda: calls.append(1) or 42)
        assert v1 == v2 == 42
        assert len(calls) == 1

    def test_invalidate_namespace(self):
        cache = CacheLayer()
        cache.set("ns", "a", 1)
        cache.set("ns", "b", 2)
        assert cache.invalidate("ns") == 2
        assert cache.get("ns", "a") is None


class TestNotificationCenter:
    def test_delivery(self):
        nc = NotificationCenter()
        received = []
        nc.add_channel("app", lambda n: received.append(n) or True)
        nc.notify("Alert", "something", severity="warning")
        assert len(received) == 1

    def test_severity_filter(self):
        nc = NotificationCenter()
        received = []
        nc.add_channel("crit-only", lambda n: received.append(n) or True, min_severity="critical")
        nc.notify("Low", "info event", severity="info")
        assert received == []

    def test_dedupe(self):
        nc = NotificationCenter(dedupe_window_s=60)
        nc.add_channel("app", lambda n: True)
        nc.notify("Same", "body", source="s")
        result = nc.notify("Same", "body", source="s")
        assert result["status"] == "deduplicated"

    def test_retry_queue(self):
        nc = NotificationCenter()
        nc.add_channel("bad", lambda n: False)
        nc.notify("X", "y")
        assert nc.card()["retry_queue"] == 1
