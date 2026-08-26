"""Tests for health probes and metrics."""

from skeleton.observability import HealthRegistry, MetricsRegistry, probe


class TestHealth:
    def test_liveness_and_readiness(self):
        health = HealthRegistry()

        @probe("ok")
        def ok():
            return {"ok": True, "detail": "fine"}

        @probe("boom")
        def boom():
            raise RuntimeError("nope")

        health.add_liveness(ok)
        health.add_readiness(ok)
        health.add_readiness(boom)
        live = health.liveness()
        ready = health.readiness()
        assert live["status"] == "up"
        assert ready["status"] == "down"
        assert any(not p["ok"] for p in ready["probes"])


class TestMetrics:
    def test_counter_and_snapshot(self):
        registry = MetricsRegistry()
        registry.counter("http.requests", "count of requests").inc()
        snap = registry.snapshot()
        assert "http.requests" in snap["counters"]
        text = registry.prometheus()
        assert "http.requests" in text
