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
        assert health.liveness()["status"] == "up"
        assert health.readiness()["status"] == "down"


class TestMetrics:
    def test_counter_and_snapshot(self):
        registry = MetricsRegistry()
        registry.counter("http.requests", "count of requests").inc()
        snap = registry.snapshot()
        assert "http.requests" in snap["counters"]
        assert "http.requests" in registry.prometheus()
