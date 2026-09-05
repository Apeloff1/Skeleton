"""Integration tests for new observability, resilience, and orchestration subsystems.

Covers distributed tracing, audit logging, event sourcing, operator
dashboard, push server, load shedder, health probes, feature flags,
rate limiter, config manager, schema registry, secret manager,
auto-scaler, anomaly detector, metrics exporter, and pipeline orchestrator.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from skeleton.cortex.operator_dashboard import OperatorDashboard
from skeleton.cortex.push_server import DashboardPushServer
from skeleton.observability.audit_logging import AuditLog
from skeleton.observability.distributed_tracing import SpanContext, Tracer
from skeleton.observability.event_sourcing import EventStore
from skeleton.observability.anomaly_detector import AnomalyDetector, AnomalyConfig
from skeleton.observability.metrics_exporter import MetricsExporter
from skeleton.organism.config_manager import ConfigManager
from skeleton.organism.feature_flags import FeatureFlagRegistry
from skeleton.organism.schema_registry import SchemaRegistry
from skeleton.organism.secret_manager import SecretManager
from skeleton.resilience.health_probes import HealthProbeAggregator, ProbeResult
from skeleton.resilience.load_shedder import LoadShedder, SheddingPolicy
from skeleton.resilience.rate_limiter import RateLimiter
from skeleton.resilience.auto_scaler import AutoScaler, ScalingPolicy
from skeleton.intelligence.pipeline_orchestrator import PipelineOrchestrator, PipelineStage


# ── Distributed Tracing ───────────────────────────────────

class TestDistributedTracing:
    def test_span_creation_and_finish(self):
        tracer = Tracer("test", sample_rate=1.0)
        span = tracer.start_span("op")
        span.add_event("mid", {"k": "v"})
        tracer.finish_span(span, {"status": "ok"})
        assert span.duration_ms() >= 0
        assert len(span.events) == 1
        flushed = tracer.flush()
        assert len(flushed) == 1
        assert flushed[0]["name"] == "op"

    def test_context_propagation(self):
        tracer = Tracer("test", sample_rate=1.0)
        span = tracer.start_span("parent")
        carrier: dict = {}
        tracer.inject_context(carrier)
        assert "skeleton-trace-id" in carrier
        extracted = tracer.extract_context(carrier)
        assert extracted is not None
        assert extracted.trace_id == span.context.trace_id

    def test_sampling(self):
        tracer = Tracer("test", sample_rate=0.0)
        span = tracer.start_span("unsampled")
        assert not span.context.sampled

    def test_nested_spans(self):
        tracer = Tracer("test", sample_rate=1.0)
        parent = tracer.start_span("parent")
        child = tracer.start_span("child", parent=parent.context)
        tracer.finish_span(child)
        tracer.finish_span(parent)
        flushed = tracer.flush()
        assert len(flushed) == 2
        parent_dict = [f for f in flushed if f["name"] == "parent"][0]
        assert len(parent_dict["children"]) == 1


# ── Audit Logging ───────────────────────────────────────

class TestAuditLogging:
    def test_record_and_query(self):
        with tempfile.TemporaryDirectory() as td:
            log = AuditLog(root=Path(td))
            entry = log.record("operator", "policy_change", "threshold", {"old": 0.5, "new": 0.7})
            assert entry.entry_hash
            results = log.query(actor="operator", action="policy_change")
            assert len(results) == 1
            assert results[0]["resource"] == "threshold"

    def test_integrity_verification(self):
        with tempfile.TemporaryDirectory() as td:
            log = AuditLog(root=Path(td))
            log.record("a", "act", "res", {})
            log.record("b", "act2", "res2", {})
            integrity = log.verify_integrity()
            assert integrity["intact"]
            assert integrity["total_entries"] == 2

    def test_integrity_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            log = AuditLog(root=Path(td))
            log.record("a", "act", "res", {})
            file_path = Path(td) / ".skeleton" / "audit.jsonl"
            lines = file_path.read_text().strip().splitlines()
            data = __import__("json").loads(lines[0])
            data["actor"] = "tampered"
            file_path.write_text(__import__("json").dumps(data) + "\n")
            log2 = AuditLog(root=Path(td))
            integrity = log2.verify_integrity()
            assert not integrity["intact"]


# ── Event Sourcing ──────────────────────────────────────

class TestEventSourcing:
    def test_append_and_replay(self):
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(root=Path(td))
            store.append("agg-1", "created", {"name": "test"})
            store.append("agg-1", "updated", {"value": 42})
            events = store.get_events("agg-1")
            assert len(events) == 2
            assert events[0].sequence == 1
            assert events[1].sequence == 2

    def test_replay_projection(self):
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(root=Path(td))
            store.append("agg-1", "add", {"amount": 5})
            store.append("agg-1", "add", {"amount": 3})
            result = store.replay("agg-1", lambda state, e: state + e.payload.get("amount", 0), 0)
            assert result == 8

    def test_snapshot_restore(self):
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(root=Path(td))
            store.append("agg-1", "add", {"amount": 5})
            store.snapshot("agg-1", {"total": 5})
            store.append("agg-1", "add", {"amount": 3})
            restored = store.restore("agg-1", lambda state, e: state + e.payload.get("amount", 0), 0)
            assert restored == 8


# ── Operator Dashboard ──────────────────────────────────

class TestOperatorDashboard:
    def test_dashboard_card(self):
        with tempfile.TemporaryDirectory() as td:
            dash = OperatorDashboard(root=Path(td))
            card = dash.card()
            assert card["kind"] == "operator-dashboard"
            assert "product" in card
            assert "nervous" in card
            assert "doctor" in card

    def test_alert_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            dash = OperatorDashboard(root=Path(td))
            alert = dash.fire_alert("warning", "repair", "test warning")
            assert alert.severity == "warning"
            active = dash.active_alerts()
            assert len(active) == 1
            dash.acknowledge_alert(alert.id)
            acked = [a for a in dash.active_alerts() if a["acknowledged"]]
            assert len(acked) == 1
            dash.resolve_alert(alert.id)
            assert len(dash.active_alerts()) == 0

    def test_subscriber_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            dash = OperatorDashboard(root=Path(td))
            received: list = []
            dash.subscribe(lambda card: received.append(card))
            dash.refresh()
            assert len(received) >= 1


# ── Push Server ─────────────────────────────────────────

@pytest.mark.asyncio
class TestPushServer:
    async def test_connect_and_broadcast(self):
        with tempfile.TemporaryDirectory() as td:
            dash = OperatorDashboard(root=Path(td))
            server = DashboardPushServer(dash, interval_s=0.1)
            received: list = []
            server.connect(lambda card: received.append(card))
            server.start()
            await asyncio.sleep(0.25)
            server.stop()
            assert len(received) >= 1
            assert received[0]["kind"] == "operator-dashboard"

    async def test_alert_broadcast(self):
        with tempfile.TemporaryDirectory() as td:
            dash = OperatorDashboard(root=Path(td))
            server = DashboardPushServer(dash)
            received: list = []
            server.connect(lambda card: received.append(card))
            server.broadcast_alert("critical", "test", "alert msg")
            assert any(r.get("kind") == "alert" for r in received)


# ── Load Shedder ────────────────────────────────────────

class TestLoadShedder:
    def test_admit_under_normal_load(self):
        shedder = LoadShedder("test", SheddingPolicy(max_latency_ms=1000, max_error_rate=0.5, max_queue_depth=200))
        shedder.record_request(50.0, error=False)
        assert shedder.admit()

    def test_shed_on_high_latency(self):
        shedder = LoadShedder("test", SheddingPolicy(max_latency_ms=10, max_error_rate=0.5, max_queue_depth=200))
        shedder.record_request(100.0, error=False)
        assert not shedder.admit()

    def test_shed_on_high_error_rate(self):
        shedder = LoadShedder("test", SheddingPolicy(max_latency_ms=1000, max_error_rate=0.1, max_queue_depth=200))
        for _ in range(20):
            shedder.record_request(10.0, error=True)
        assert not shedder.admit()

    def test_card(self):
        shedder = LoadShedder("test")
        shedder.record_request(25.0, error=False)
        card = shedder.card()
        assert card["kind"] == "load-shedder-card"
        assert card["mean_latency_ms"] == 25.0


# ── Health Probes ─────────────────────────────────────────

class TestHealthProbes:
    def test_probe_registration_and_run(self):
        agg = HealthProbeAggregator()
        agg.register("db", lambda: ProbeResult("db", True, 5.0, "ok", 0))
        agg.register("cache", lambda: ProbeResult("cache", True, 2.0, "ok", 0), depends_on=["db"])
        result = agg.run_all()
        assert result["readiness"]
        assert len(result["probes"]) == 2

    def test_dependency_failure(self):
        agg = HealthProbeAggregator()
        agg.register("db", lambda: ProbeResult("db", False, 0.0, "down", 0))
        agg.register("cache", lambda: ProbeResult("cache", True, 2.0, "ok", 0), depends_on=["db"])
        result = agg.run_all()
        assert not result["readiness"]
        assert "cache" in result["unhealthy"]

    def test_liveness(self):
        agg = HealthProbeAggregator()
        assert not agg.liveness()
        agg.register("x", lambda: ProbeResult("x", True, 0.0, "ok", 0))
        agg.run_all()
        assert agg.liveness()


# ── Feature Flags ─────────────────────────────────────────

class TestFeatureFlags:
    def test_flag_registration_and_evaluation(self):
        with tempfile.TemporaryDirectory() as td:
            reg = FeatureFlagRegistry(root=Path(td))
            reg.register("new-ui", enabled=True, percentage=100.0)
            assert reg.is_enabled("new-ui")
            assert not reg.is_enabled("missing-flag")

    def test_percentage_rollout(self):
        with tempfile.TemporaryDirectory() as td:
            reg = FeatureFlagRegistry(root=Path(td))
            reg.register("partial", enabled=True, percentage=50.0)
            assert reg.is_enabled("partial", {"session_id": "session-a"}) in (True, False)

    def test_targeting(self):
        with tempfile.TemporaryDirectory() as td:
            reg = FeatureFlagRegistry(root=Path(td))
            reg.register("beta", enabled=True, percentage=0.0, targets={"user_id": ["u1"]})
            assert reg.is_enabled("beta", {"user_id": "u1"})
            assert not reg.is_enabled("beta", {"user_id": "u2"})

    def test_dependencies(self):
        with tempfile.TemporaryDirectory() as td:
            reg = FeatureFlagRegistry(root=Path(td))
            reg.register("parent", enabled=True, percentage=100.0)
            reg.register("child", enabled=True, percentage=100.0, dependencies=["parent"])
            assert reg.is_enabled("child", {"flag:parent": True})
            assert not reg.is_enabled("child", {"flag:parent": False})


# ── Rate Limiter ──────────────────────────────────────────

class TestRateLimiter:
    def test_allow_within_capacity(self):
        rl = RateLimiter(capacity=5, refill_rate=1.0)
        for _ in range(5):
            assert rl.allow("key1")
        assert not rl.allow("key1")

    def test_refill_over_time(self):
        rl = RateLimiter(capacity=1, refill_rate=10.0)
        assert rl.allow("key1")
        assert not rl.allow("key1")
        __import__("time").sleep(0.15)
        assert rl.allow("key1")

    def test_per_key_isolation(self):
        rl = RateLimiter(capacity=1, refill_rate=10.0)
        assert rl.allow("key1")
        assert rl.allow("key2")

    def test_wait_time(self):
        rl = RateLimiter(capacity=1, refill_rate=1.0)
        rl.allow("key1")
        wait = rl.wait_time("key1")
        assert wait > 0


# ── Config Manager ────────────────────────────────────────

class TestConfigManager:
    def test_layered_get(self):
        with tempfile.TemporaryDirectory() as td:
            cm = ConfigManager(root=Path(td))
            cm.set("a.b", 42)
            assert cm.get("a.b") == 42
            assert cm.get("a.missing", "default") == "default"

    def test_callback_on_change(self):
        with tempfile.TemporaryDirectory() as td:
            cm = ConfigManager(root=Path(td))
            changes: list = []
            cm.on_change(lambda path, old, new: changes.append((path, old, new)))
            cm.set("x", 1)
            assert changes == [("x", None, 1)]

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("SKELETON_FOO__BAR", "99")
        cm = ConfigManager()
        assert cm.get("foo.bar") == 99

    def test_card(self):
        cm = ConfigManager()
        card = cm.card()
        assert card["kind"] == "config-card"


# ── Schema Registry ───────────────────────────────────────

class TestSchemaRegistry:
    def test_register_and_validate(self):
        reg = SchemaRegistry()
        reg.register("user", 1, {
            "required": ["name"],
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
        })
        errors = reg.validate("user", {"name": "Alice", "age": 30})
        assert errors == []
        errors = reg.validate("user", {"age": 30})
        assert any("missing required field: name" in e for e in errors)

    def test_type_validation(self):
        reg = SchemaRegistry()
        reg.register("item", 1, {
            "properties": {"count": {"type": "int"}},
        })
        errors = reg.validate("item", {"count": "not_a_number"})
        assert any("count" in e for e in errors)

    def test_migration(self):
        reg = SchemaRegistry()
        reg.register("data", 1, {})
        reg.register("data", 2, {})
        reg.register_migration("data", 1, 2, lambda d: {**d, "version": 2})
        result = reg.migrate("data", {"name": "x"}, 1, 2)
        assert result["version"] == 2

    def test_card(self):
        reg = SchemaRegistry()
        reg.register("a", 1, {})
        reg.register("a", 2, {})
        card = reg.card()
        assert card["schemas"]["a"] == [1, 2]


# ── Secret Manager ────────────────────────────────────────

class TestSecretManager:
    def test_set_and_get(self):
        with tempfile.TemporaryDirectory() as td:
            sm = SecretManager(root=Path(td), master_secret="test-key-123")
            sm.set("api_key", "secret123")
            assert sm.get("api_key") == "secret123"

    def test_versioning(self):
        with tempfile.TemporaryDirectory() as td:
            sm = SecretManager(root=Path(td), master_secret="test-key-123")
            sm.set("token", "v1")
            sm.set("token", "v2")
            assert sm.get("token") == "v2"

    def test_rotation(self):
        with tempfile.TemporaryDirectory() as td:
            sm = SecretManager(root=Path(td), master_secret="test-key-123")
            sm.set("token", "old")
            sm.rotate("token", "new")
            assert sm.get("token") == "new"

    def test_card(self):
        with tempfile.TemporaryDirectory() as td:
            sm = SecretManager(root=Path(td), master_secret="test-key-123")
            card = sm.card()
            assert card["kind"] == "secret-manager-card"


# ── Auto Scaler ───────────────────────────────────────────

class TestAutoScaler:
    def test_scale_up(self):
        scaler = AutoScaler("test", ScalingPolicy(min_workers=1, max_workers=5, target_latency_ms=50.0))
        result = scaler.evaluate(200.0, 0.9)
        assert result["action"] == "scale_up"
        assert result["workers"] == 2

    def test_scale_down(self):
        scaler = AutoScaler("test", ScalingPolicy(min_workers=2, max_workers=5, target_latency_ms=50.0))
        scaler.evaluate(200.0, 0.9)  # scale up first
        result = scaler.evaluate(10.0, 0.2)
        assert result["action"] == "scale_down"
        assert result["workers"] == 1

    def test_cooldown(self):
        scaler = AutoScaler("test", ScalingPolicy(min_workers=1, max_workers=5, target_latency_ms=50.0, cooldown_s=60.0))
        scaler.evaluate(200.0, 0.9)
        result = scaler.evaluate(200.0, 0.9)
        assert result["action"] == "cooldown"

    def test_card(self):
        scaler = AutoScaler("test")
        card = scaler.card()
        assert card["kind"] == "auto-scaler-card"
        assert card["current_workers"] == 1


# ── Anomaly Detector ──────────────────────────────────────

class TestAnomalyDetector:
    def test_zscore_detection(self):
        detector = AnomalyDetector("latency", AnomalyConfig(method="zscore", zscore_threshold=2.0))
        for i in range(20):
            detector.feed(10.0)
        anomaly = detector.feed(100.0)
        assert anomaly is not None
        assert anomaly["method"] == "zscore"

    def test_iqr_detection(self):
        detector = AnomalyDetector("errors", AnomalyConfig(method="iqr", iqr_multiplier=1.5))
        for i in range(20):
            detector.feed(float(i))
        anomaly = detector.feed(100.0)
        assert anomaly is not None
        assert anomaly["method"] == "iqr"

    def test_ema_detection(self):
        detector = AnomalyDetector("traffic", AnomalyConfig(method="ema", ema_alpha=0.3, ema_threshold_multiplier=2.0))
        for i in range(20):
            detector.feed(10.0)
        anomaly = detector.feed(50.0)
        assert anomaly is not None
        assert anomaly["method"] == "ema"

    def test_no_anomaly_normal(self):
        detector = AnomalyDetector("normal", AnomalyConfig(method="zscore"))
        for i in range(20):
            result = detector.feed(10.0 + i * 0.1)
            assert result is None

    def test_card(self):
        detector = AnomalyDetector("test")
        card = detector.card()
        assert card["kind"] == "anomaly-detector-card"


# ── Metrics Exporter ────────────────────────────────────

class TestMetricsExporter:
    def test_counter_rendering(self):
        exporter = MetricsExporter("test")
        exporter.counter("requests", 1.0)
        exporter.counter("requests", 2.0)
        rendered = exporter.render()
        assert "requests 3.0" in rendered

    def test_gauge_rendering(self):
        exporter = MetricsExporter("test")
        exporter.gauge("temperature", 42.0, {"host": "a"})
        rendered = exporter.render()
        assert "temperature{host=\"a\"} 42.0" in rendered

    def test_histogram_rendering(self):
        exporter = MetricsExporter("test")
        exporter.histogram("duration", 0.05, buckets=[0.01, 0.05, 0.1])
        exporter.histogram("duration", 0.2, buckets=[0.01, 0.05, 0.1])
        rendered = exporter.render()
        assert "duration_bucket" in rendered
        assert "duration_count 2" in rendered

    def test_card(self):
        exporter = MetricsExporter("test")
        card = exporter.card()
        assert card["kind"] == "metrics-exporter-card"


# ── Pipeline Orchestrator ─────────────────────────────────

class TestPipelineOrchestrator:
    def test_linear_pipeline(self):
        orch = PipelineOrchestrator("test")
        orch.add_stage(PipelineStage("stage1", lambda x: x + 1))
        orch.add_stage(PipelineStage("stage2", lambda x: x * 2, dependencies=["stage1"]))
        result = orch.execute(5)
        assert result["successful"] == 2
        assert result["failed"] == 0
        stage_results = result["stages"]
        assert stage_results["stage1"]["output"] == 6
        assert stage_results["stage2"]["output"] == 12

    def test_parallel_stages(self):
        orch = PipelineOrchestrator("test")
        orch.add_stage(PipelineStage("a", lambda x: x + 1))
        orch.add_stage(PipelineStage("b", lambda x: x * 2))
        orch.add_stage(PipelineStage("c", lambda inputs: inputs["a"] + inputs["b"], dependencies=["a", "b"]))
        result = orch.execute(5)
        assert result["successful"] == 3
        stage_results = result["stages"]
        assert stage_results["c"]["output"] == 16  # (5+1) + (5*2) = 6 + 10 = 16

    def test_failed_stage(self):
        orch = PipelineOrchestrator("test")
        orch.add_stage(PipelineStage("fail", lambda x: (_ for _ in ()).throw(ValueError("boom"))))
        result = orch.execute(5)
        assert result["failed"] == 1
        assert result["stages"]["fail"]["success"] is False

    def test_card(self):
        orch = PipelineOrchestrator("test")
        orch.add_stage(PipelineStage("s", lambda x: x))
        card = orch.card()
        assert card["kind"] == "pipeline-card"
        assert card["total_stages"] == 1
