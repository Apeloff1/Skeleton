"""Tests for wave 4: dependency graph, vuln scanner, eval framework,
knowledge base, API gateway, service discovery, task queue, webhooks,
canary controller, and cost tracker.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from skeleton.api.gateway import APIGateway, GatewayRequest
from skeleton.core.task_queue import TaskQueue
from skeleton.deployment.canary import CanaryController
from skeleton.intelligence.eval_framework import EvalSuite
from skeleton.intelligence.knowledge_base import KnowledgeBase
from skeleton.integrations.webhooks import WebhookSystem
from skeleton.mesh.dependency_graph import DependencyGraph
from skeleton.mesh.service_discovery import ServiceRegistry
from skeleton.observability.cost_tracker import CostTracker
from skeleton.security.vuln_scanner import VulnScanner
from skeleton.security.rbac import RBACRegistry
from skeleton.data.cache_layer import CacheLayer


class TestDependencyGraph:
    def test_topo_order(self):
        g = DependencyGraph()
        g.add_edge("api", "db")
        g.add_edge("api", "cache")
        order = g.topological_order()
        assert order.index("db") < order.index("api")

    def test_blast_radius(self):
        g = DependencyGraph()
        g.add_edge("api", "db")
        g.add_edge("worker", "db")
        g.add_edge("dashboard", "api")
        blast = g.blast_radius("db")
        assert set(blast["affected"]) == {"api", "worker", "dashboard"}
        assert blast["critical"]

    def test_cycle_detection(self):
        g = DependencyGraph()
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        assert g.cycles()

    def test_no_cycles(self):
        g = DependencyGraph()
        g.add_edge("a", "b")
        assert g.cycles() == []


class TestVulnScanner:
    def test_scan_finds_default_secret(self):
        with tempfile.TemporaryDirectory() as td:
            scanner = VulnScanner(root=Path(td))
            card = scanner.scan()
            checks = [f["check"] for f in card["findings"]]
            assert "default-master-secret" in checks

    def test_score_drops_with_findings(self):
        with tempfile.TemporaryDirectory() as td:
            scanner = VulnScanner(root=Path(td))
            scanner.scan()
            assert scanner.score() < 100.0

    def test_custom_rule(self):
        with tempfile.TemporaryDirectory() as td:
            scanner = VulnScanner(root=Path(td))
            scanner.add_rule("test-rule", "low", lambda r: "issue found", "fix it")
            card = scanner.scan()
            assert any(f["check"] == "test-rule" for f in card["findings"])


class TestEvalFramework:
    def test_run_and_pass_rate(self):
        suite = EvalSuite("basic")
        suite.case("c1", {"x": 1}, lambda out: out > 0)
        suite.case("c2", {"x": -1}, lambda out: out > 0)
        report = suite.run(lambda inp: inp["x"])
        assert report["pass_rate"] == 0.5

    def test_regression_detection(self):
        with tempfile.TemporaryDirectory() as td:
            suite = EvalSuite("reg", root=Path(td))
            suite.case("c1", {"x": 1}, lambda out: out > 0)
            report1 = suite.run(lambda inp: inp["x"])
            suite.save_baseline(report1)
            report2 = suite.run(lambda inp: -1)
            assert "c1" in report2["regressions"]

    def test_tag_filter(self):
        suite = EvalSuite("tags")
        suite.case("fast", {"x": 1}, lambda o: True, tags=["smoke"])
        suite.case("slow", {"x": 1}, lambda o: False, tags=["nightly"])
        report = suite.run(lambda inp: inp, tags=["smoke"])
        assert report["ran"] == 1
        assert report["passed"] == 1


class TestKnowledgeBase:
    def test_put_and_get(self):
        with tempfile.TemporaryDirectory() as td:
            kb = KnowledgeBase(root=Path(td))
            kb.put("rb-1", "Restart runbook", "Steps to restart the api service", tags=["runbook"], subsystems=["api"])
            doc = kb.get("rb-1")
            assert doc is not None
            assert doc.version == 1

    def test_versioning(self):
        with tempfile.TemporaryDirectory() as td:
            kb = KnowledgeBase(root=Path(td))
            kb.put("d1", "Title", "v1 body")
            kb.put("d1", "Title", "v2 body")
            assert kb.get("d1").version == 2

    def test_search_ranking(self):
        with tempfile.TemporaryDirectory() as td:
            kb = KnowledgeBase(root=Path(td))
            kb.put("a", "Database failover", "How to fail over the database")
            kb.put("b", "Cache tuning", "Database connection pool sizing")
            hits = kb.search("database failover")
            assert hits[0]["doc_id"] == "a"

    def test_for_subsystem(self):
        with tempfile.TemporaryDirectory() as td:
            kb = KnowledgeBase(root=Path(td))
            kb.put("x", "Doc", "body", subsystems=["api"])
            assert len(kb.for_subsystem("api")) == 1
            assert kb.for_subsystem("db") == []


class TestAPIGateway:
    def test_routing(self):
        gw = APIGateway()
        gw.route("/health", lambda p: {"ok": True})
        resp = gw.handle(GatewayRequest(path="/health"))
        assert resp.status == 200
        assert resp.body == {"ok": True}

    def test_404(self):
        gw = APIGateway()
        resp = gw.handle(GatewayRequest(path="/missing"))
        assert resp.status == 404

    def test_rbac_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            rbac = RBACRegistry(root=Path(td))
            gw = APIGateway(rbac=rbac)
            gw.route("/admin", lambda p: {}, scope="policy", action="write")
            resp = gw.handle(GatewayRequest(path="/admin", actor="nobody"))
            assert resp.status == 403

    def test_rate_limit(self):
        gw = APIGateway()
        gw.route("/limited", lambda p: {}, rate_limit_per_s=1)
        assert gw.handle(GatewayRequest(path="/limited")).status == 200
        assert gw.handle(GatewayRequest(path="/limited")).status == 429

    def test_caching(self):
        cache = CacheLayer()
        gw = APIGateway(cache=cache)
        calls = []
        gw.route("/cached", lambda p: calls.append(1) or {"n": len(calls)}, cache_ttl_s=60)
        r1 = gw.handle(GatewayRequest(path="/cached"))
        r2 = gw.handle(GatewayRequest(path="/cached"))
        assert r2.cached
        assert len(calls) == 1

    def test_error_handling(self):
        gw = APIGateway()
        def boom(p):
            raise ValueError("x")
        gw.route("/err", boom)
        resp = gw.handle(GatewayRequest(path="/err"))
        assert resp.status == 500


class TestServiceDiscovery:
    def test_register_lookup(self):
        reg = ServiceRegistry()
        reg.register("i1", "api", "10.0.0.1:8000", capabilities=["http"])
        hits = reg.lookup("api", capability="http")
        assert len(hits) == 1

    def test_heartbeat_expiry(self):
        reg = ServiceRegistry(ttl_s=0.01)
        reg.register("i2", "db", "10.0.0.2:5432")
        import time as _t
        _t.sleep(0.02)
        assert reg.lookup("db") == []

    def test_least_loaded_pick(self):
        reg = ServiceRegistry()
        reg.register("a", "svc", "h1")
        reg.register("b", "svc", "h2")
        reg.heartbeat("a", load=0.9)
        reg.heartbeat("b", load=0.1)
        pick = reg.pick("svc", strategy="least_loaded")
        assert pick["instance_id"] == "b"

    def test_round_robin(self):
        reg = ServiceRegistry()
        reg.register("a", "svc", "h1")
        reg.register("b", "svc", "h2")
        first = reg.pick("svc")
        second = reg.pick("svc")
        assert first["instance_id"] != second["instance_id"]


class TestTaskQueue:
    def test_enqueue_dequeue_ack(self):
        q = TaskQueue()
        task = q.enqueue("work", {"n": 1})
        got = q.dequeue("work")
        assert got.task_id == task.task_id
        assert q.ack(got.task_id)
        assert q.card()["completed"] == 1

    def test_priority_order(self):
        q = TaskQueue()
        q.enqueue("p", {"p": "low"}, priority=1)
        q.enqueue("p", {"p": "high"}, priority=10)
        got = q.dequeue("p")
        assert got.payload["p"] == "high"

    def test_nack_requeue(self):
        q = TaskQueue()
        q.enqueue("r", {"x": 1})
        task = q.dequeue("r")
        q.nack(task.task_id, requeue=True)
        assert q.depth("r") == 1

    def test_dead_letter_after_max_attempts(self):
        q = TaskQueue()
        q.enqueue("dl", {"x": 1}, max_attempts=1)
        task = q.dequeue("dl")
        q.nack(task.task_id, requeue=True)
        assert len(q.dead_letters("dl")) == 1

    def test_delayed_task_not_visible(self):
        q = TaskQueue()
        q.enqueue("delay", {"x": 1}, delay_s=999)
        assert q.dequeue("delay") is None


class TestWebhooks:
    def test_publish_and_deliver(self):
        sent = []
        wh = WebhookSystem(sender=lambda url, payload, sig: sent.append((url, sig)) or True)
        wh.subscribe("alerts", "https://example.com/hook", secret="s3")
        wh.publish("alerts", {"msg": "hi"})
        delivered = wh.process_pending()
        assert delivered == 1
        assert len(sent) == 1
        assert sent[0][1]  # signature present

    def test_topic_filtering(self):
        wh = WebhookSystem()
        wh.subscribe("a", "https://x.com/a")
        deliveries = wh.publish("b", {"k": 1})
        assert deliveries == []

    def test_failed_delivery_retries(self):
        wh = WebhookSystem(sender=lambda u, p, s: False)
        wh.subscribe("t", "https://x.com")
        wh.publish("t", {})
        wh.process_pending()
        card = wh.card()
        assert card["pending"] == 1  # still pending with backoff

    def test_dead_after_max_attempts(self):
        wh = WebhookSystem(sender=lambda u, p, s: False)
        sub = wh.subscribe("t", "https://x.com")
        wh.publish("t", {})
        for _ in range(5):
            import time as _t
            _t.sleep(0.01)
            for d in wh._deliveries.values():
                d.next_attempt_ns = 0
            wh.process_pending()
        assert wh.card()["dead"] == 1

    def test_replay(self):
        wh = WebhookSystem()
        wh.subscribe("t", "https://x.com")
        wh.publish("t", {"n": 1})
        wh.publish("t", {"n": 2})
        count = wh.replay("t")
        assert count == 2


class TestCanary:
    def test_progression_to_promotion(self):
        canary = CanaryController()
        r = canary.start("api", "1.0", "2.0", stages=[10, 50, 100], baseline_latency_ms=100)
        canary.observe(r.rollout_id, 0.01, 90)
        canary.observe(r.rollout_id, 0.01, 95)
        final = canary.observe(r.rollout_id, 0.01, 92)
        assert final["action"] == "promoted"

    def test_auto_rollback_on_errors(self):
        canary = CanaryController(max_error_rate=0.05)
        r = canary.start("api", "1.0", "2.0", baseline_latency_ms=100)
        result = canary.observe(r.rollout_id, 0.5, 90)
        assert result["action"] == "rolled_back"

    def test_auto_rollback_on_latency(self):
        canary = CanaryController(max_latency_regression=1.5)
        r = canary.start("api", "1.0", "2.0", baseline_latency_ms=100)
        result = canary.observe(r.rollout_id, 0.0, 500)
        assert result["action"] == "rolled_back"

    def test_pause_resume(self):
        canary = CanaryController()
        r = canary.start("api", "1.0", "2.0")
        assert canary.pause(r.rollout_id)
        assert canary.resume(r.rollout_id)


class TestCostTracker:
    def test_record_and_spend(self):
        ct = CostTracker(daily_budget_usd=5.0)
        ct.record("api", "compute_second", 1000)
        assert ct.spend_today() > 0

    def test_by_subsystem(self):
        ct = CostTracker()
        ct.record("api", "compute_second", 100)
        ct.record("db", "compute_second", 50)
        by_sub = ct.by_subsystem()
        assert by_sub["api"] > by_sub["db"]

    def test_budget_status(self):
        ct = CostTracker(daily_budget_usd=0.001)
        ct.record("api", "compute_second", 100000)
        status = ct.budget_status()
        assert status["over_budget"]

    def test_monthly_projection(self):
        ct = CostTracker()
        ct.record("api", "compute_second", 1000)
        assert ct.monthly_projection() == round(ct.spend_today() * 30, 2)
