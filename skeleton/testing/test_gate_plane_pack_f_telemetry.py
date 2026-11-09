"""Pack F — per-gate metrics and trace spans over skeleton.observability."""

from __future__ import annotations

import pytest

from skeleton.gate_plane.admit import AdmissionMatrix
from skeleton.gate_plane.backpressure import BackpressureGate, BackpressureStage, StaticSource
from skeleton.gate_plane.backpressure.snapshot import iso_now
from skeleton.gate_plane.pipeline import (
    BreakerConfig,
    BreakerOpenError,
    BreakerRegistry,
    BreakerStage,
    CircuitBreaker,
    Pipeline,
    PipelineRequest,
    PipelineResponse,
    PipelineRouter,
    RetrySpec,
    RetryStage,
    RouteConfig,
    RouteTable,
)
from skeleton.gate_plane.s2s.authz import default_gate_plane_policies
from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.gate import S2SAuthGate
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.tokens import TokenSigner, TokenVerifier
from skeleton.gate_plane.telemetry import (
    M_BP_DECISIONS,
    M_BP_LOAD,
    M_BREAKER_STATE,
    M_BREAKER_TRANSITIONS,
    M_PIPE_ERRORS,
    M_PIPE_IN_FLIGHT,
    M_PIPE_REQUESTS,
    M_PIPE_RETRIES,
    M_S2S_DECISIONS,
    M_S2S_TOKEN_ERRORS,
    SPAN_PIPELINE,
    SPAN_S2S,
    GateTelemetry,
    TelemetryStage,
    format_traceparent,
    parse_traceparent,
    safe_label,
    status_class,
)
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor
from skeleton.observability.metrics import MetricsCollector
from skeleton.observability.tracing import InMemoryExporter, Tracer

GET = PipelineRequest("GET", "/api/v1/forge/1")
SECRET = b"s" * 32


def tel(clock=None):
    return GateTelemetry(metrics=MetricsCollector(), tracer=Tracer("gate_plane", InMemoryExporter()), clock=clock)


def ok(_r, _c):
    return PipelineResponse(200)


class TestHelpers:
    def test_safe_label(self):
        assert safe_label(None) == "none"
        assert safe_label("a b/c{d}") == "a_b_c_d_"
        assert len(safe_label("x" * 500)) == 64
        assert safe_label("") == "none"

    @pytest.mark.parametrize("s,c", [(200, "2xx"), (429, "4xx"), (503, "5xx"), (99, "other"), (600, "other")])
    def test_status_class(self, s, c):
        assert status_class(s) == c

    def test_traceparent_roundtrip(self):
        t = Tracer("x")
        span = t.start_span("s")
        tp = format_traceparent(span)
        parsed = parse_traceparent(tp)
        assert parsed == (span.trace_id, span.span_id)

    @pytest.mark.parametrize(
        "bad",
        [None, "", "garbage", "01-" + "a" * 32 + "-" + "b" * 16 + "-01", "00-" + "0" * 32 + "-" + "b" * 16 + "-01",
         "00-" + "a" * 32 + "-" + "0" * 16 + "-01"],
    )
    def test_traceparent_rejects(self, bad):
        assert parse_traceparent(bad) is None

    def test_format_traceparent_non_hex_trace(self):
        t = Tracer("x")
        span = t.start_span("s", trace_id="not-hex")
        tp = format_traceparent(span)
        assert parse_traceparent(tp) is not None


class TestPipelineTelemetry:
    def test_request_metrics_and_span(self):
        c = ManualClock()
        t = tel(c)
        p = Pipeline([TelemetryStage(t)], route="forge-read", upstream="forge", clock=c)

        def h(req, ctx):
            c.advance(0.25)
            assert ctx.attrs["traceparent"].startswith("00-")
            return PipelineResponse(200)

        p.run(GET, h)
        assert t.counter(M_PIPE_REQUESTS, route="forge-read", method="GET", status_class="2xx") == 1
        snap = t.snapshot()
        lat = snap["histograms"]["gate_plane.pipeline.latency_ms{route=forge-read}"]
        assert lat["max"] == pytest.approx(250.0)
        assert snap["gauges"][f"{M_PIPE_IN_FLIGHT}{{route=forge-read}}"] == 0
        spans = t.spans(SPAN_PIPELINE)
        assert len(spans) == 1
        assert spans[0].attributes["http.status"] == 200
        assert spans[0].attributes["gate.route"] == "forge-read"
        assert spans[0].status == "OK"

    def test_retries_attempts_and_events(self):
        c = ManualClock()
        t = tel(c)
        p = Pipeline([TelemetryStage(t), RetryStage(RetrySpec(max_attempts=3, jitter=0))], route="r", clock=c)
        outcomes = [503, 503, 200]
        p.run(GET, lambda req, ctx: PipelineResponse(outcomes.pop(0)))
        assert t.counter(M_PIPE_RETRIES, route="r") == 2
        span = t.spans(SPAN_PIPELINE)[0]
        assert [e["name"] for e in span.events] == ["retry", "retry"]
        assert span.attributes["gate.attempts"] == 3
        hist = t.snapshot()["histograms"]["gate_plane.pipeline.attempts{route=r}"]
        assert hist["max"] == 3

    def test_5xx_marks_span_error(self):
        c = ManualClock()
        t = tel(c)
        p = Pipeline([TelemetryStage(t)], route="r", clock=c)
        p.run(GET, lambda req, ctx: PipelineResponse(502))
        assert t.spans(SPAN_PIPELINE)[0].status == "ERROR"
        assert t.counter(M_PIPE_REQUESTS, route="r", method="GET", status_class="5xx") == 1

    def test_pipeline_error_counted_and_reraised(self):
        c = ManualClock()
        t = tel(c)
        b = CircuitBreaker("up", BreakerConfig(consecutive_failures=1, min_calls=1, window_size=1), clock=c)
        b.force_open()
        p = Pipeline([TelemetryStage(t), BreakerStage(b)], route="r", clock=c)
        with pytest.raises(BreakerOpenError):
            p.run(GET, ok)
        assert t.counter(M_PIPE_ERRORS, route="r", method="GET", error="circuit_open") == 1
        assert t.counter(M_PIPE_REQUESTS, route="r", method="GET", status_class="5xx") == 1
        span = t.spans(SPAN_PIPELINE)[0]
        assert span.status == "ERROR"
        assert span.attributes["error.type"] == "BreakerOpenError"
        assert [e["name"] for e in span.events] == ["breaker_reject"]

    def test_generic_exception_counted(self):
        c = ManualClock()
        t = tel(c)
        p = Pipeline([TelemetryStage(t)], route="r", clock=c)

        def boom(req, ctx):
            raise ValueError("nope")

        with pytest.raises(ValueError):
            p.run(GET, boom)
        assert t.counter(M_PIPE_ERRORS, route="r", method="GET", error="ValueError") == 1

    def test_inbound_traceparent_continued(self):
        c = ManualClock()
        t = tel(c)
        p = Pipeline([TelemetryStage(t)], route="r", clock=c)
        trace = "a" * 32
        req = PipelineRequest("GET", "/x", headers={"traceparent": f"00-{trace}-{'b' * 16}-01"})
        seen = {}

        def h(r, ctx):
            seen["tp"] = ctx.attrs["traceparent"]
            return PipelineResponse(200)

        p.run(req, h)
        span = t.spans(SPAN_PIPELINE)[0]
        assert span.trace_id == trace
        assert span.attributes["gate.parent_span"] == "b" * 16
        assert seen["tp"].split("-")[1] == trace

    def test_route_label_not_raw_path(self):
        c = ManualClock()
        t = tel(c)
        p = Pipeline([TelemetryStage(t)], route="forge-read", clock=c)
        p.run(PipelineRequest("GET", "/api/v1/forge/secret-job-123"), ok)
        assert not any("secret-job-123" in k for k in t.snapshot()["counters"])

    def test_broken_metrics_never_break_calls(self):
        class Broken(MetricsCollector):
            def increment(self, *a, **k):
                raise RuntimeError("x")

            def histogram(self, *a, **k):
                raise RuntimeError("x")

            def gauge(self, *a, **k):
                raise RuntimeError("x")

        c = ManualClock()
        t = GateTelemetry(metrics=Broken(), clock=c)
        p = Pipeline([TelemetryStage(t)], route="r", clock=c)
        assert p.run(GET, ok).status == 200
        assert t.dropped >= 3

    def test_router_stage_factory(self):
        c = ManualClock()
        t = tel(c)
        router = PipelineRouter(
            RouteTable([RouteConfig(name="r", pattern="/**", upstream="u")]),
            clock=c,
            stage_factories={"telemetry": t.stage_factory()},
        )
        router.call(GET, ok)
        assert t.counter(M_PIPE_REQUESTS, route="r", method="GET", status_class="2xx") == 1
        assert isinstance(t.stage(), TelemetryStage)


class TestGateHooks:
    def env(self):
        clock = ManualClock()
        ring = KeyRing(clock=clock)
        ring.add_key("k1", SECRET, activate=True)
        verifier = TokenVerifier("gateway", ring, clock=clock)
        matrix = AdmissionMatrix(gate=AdaptiveGate(100, 0), governor=ChaosGovernor(min_samples=1000))
        gate = S2SAuthGate(verifier, default_gate_plane_policies(), matrix=matrix)
        signer = TokenSigner("forge-worker", ring, clock=clock)
        return clock, gate, signer

    def test_s2s_hook_counts_outcomes(self):
        clock, gate, signer = self.env()
        t = tel(clock).attach(s2s_gate=gate)
        tok = signer.mint("gateway", ["forge:read"])
        assert gate.evaluate("GET", "/api/v1/forge/1", {"Authorization": f"Service {tok}"}).allowed
        assert not gate.evaluate("GET", "/api/v1/forge/1", {}).allowed
        assert not gate.evaluate("GET", "/api/v1/forge/1", {"Authorization": "Service nope"}).allowed
        assert t.counter(M_S2S_DECISIONS, outcome="allow", policy="forge-read", method="GET") == 1
        assert t.counter(M_S2S_DECISIONS, outcome="unauthenticated", policy="none", method="GET") == 2
        counters = t.snapshot()["counters"]
        assert any(k.startswith(M_S2S_TOKEN_ERRORS) for k in counters)
        spans = t.spans(SPAN_S2S)
        assert len(spans) == 3
        allow = [s for s in spans if s.attributes["gate.outcome"] == "allow"][0]
        assert allow.attributes["s2s.service"] == "forge-worker"
        assert allow.status == "OK"
        assert any(s.status == "ERROR" for s in spans)

    def test_s2s_hook_no_token_material_in_telemetry(self):
        clock, gate, signer = self.env()
        t = tel(clock).attach(s2s_gate=gate)
        tok = signer.mint("gateway", ["forge:read"])
        gate.evaluate("GET", "/api/v1/forge/1", {"Authorization": f"Service {tok}"})
        dumped = repr(t.snapshot()) + repr([s.to_dict() for s in t.spans()])
        assert tok not in dumped
        assert SECRET.decode() not in dumped

    def test_s2s_hook_tolerates_garbage(self):
        t = tel(ManualClock())
        t.s2s_hook("GET", "/x", object())
        assert t.counter(M_S2S_DECISIONS, outcome="unknown", policy="none", method="GET") == 1

    def test_breaker_listener(self):
        c = ManualClock()
        reg = BreakerRegistry(clock=c, default=BreakerConfig(consecutive_failures=1, min_calls=1, window_size=1, cooldown_s=5))
        t = tel(c).attach(breakers=reg)
        b = reg.get("forge")
        b.try_acquire()
        b.record_failure()
        snap = t.snapshot()
        assert snap["gauges"][f"{M_BREAKER_STATE}{{breaker=forge}}"] == 2.0
        assert t.counter(M_BREAKER_TRANSITIONS, breaker="forge", **{"from": "closed", "to": "open"}) == 1
        c.advance(5)
        assert b.try_acquire()
        b.record_success()
        assert t.snapshot()["gauges"][f"{M_BREAKER_STATE}{{breaker=forge}}"] == 0.0

    def test_backpressure_listener(self):
        c = ManualClock()
        view = {
            "schema_version": 1, "load": 0.99, "queue_depth": 1, "max_queue_depth": 10,
            "tenant_queue_depth": None, "retry_after_s": 1.0, "state": "shed", "observed_at": iso_now(c.now()),
        }
        g = BackpressureGate(StaticSource(view, name="pack_h"))
        t = tel(c).attach(backpressure=g)
        p = Pipeline([TelemetryStage(t), BackpressureStage(g)], route="r", clock=c)
        assert p.run(GET, ok).status == 429
        assert t.counter(M_BP_DECISIONS, action="shed", reason="load_shed", source="pack_h") == 1
        assert t.snapshot()["gauges"][f"{M_BP_LOAD}{{source=pack_h}}"] == 0.99
        assert t.spans(SPAN_PIPELINE)[0].attributes["gate.backpressure"] == "shed"
        assert t.counter(M_PIPE_REQUESTS, route="r", method="GET", status_class="4xx") == 1

    def test_attach_none_is_noop(self):
        t = tel()
        assert t.attach() is t
