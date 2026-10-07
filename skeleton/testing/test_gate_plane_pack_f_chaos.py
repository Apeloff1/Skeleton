"""Pack F — chaos suite (deterministic, virtual time) and one-call plane wiring."""

from __future__ import annotations

import pytest

from skeleton.gate_plane.admit import AdmissionMatrix
from skeleton.gate_plane.backpressure import StaticSource
from skeleton.gate_plane.backpressure.snapshot import iso_now
from skeleton.gate_plane.chaos_pack_f import (
    PACK_F_CHAOS_SCENARIOS,
    ChaosReport,
    FaultPlan,
    FaultyUpstream,
    run_all_pack_f_chaos,
    run_pack_f_chaos,
)
from skeleton.gate_plane.pack_f import build_pack_f_plane
from skeleton.gate_plane.pipeline import BreakerOpenError, PipelineRequest, PipelineResponse
from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.tokens import TokenSigner, TokenVerifier
from skeleton.gate_plane.telemetry import M_PIPE_REQUESTS, M_S2S_DECISIONS, SPAN_PIPELINE
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor

EXPECTED = {
    "brownout_breaker_trips",
    "retry_storm_bounded",
    "deadline_caps_latency",
    "pack_h_outage_fallback",
    "pressure_spike_sheds",
    "key_rotation_under_load",
    "flapping_upstream_backoff",
    "telemetry_failure_isolation",
}


def test_catalog_complete():
    assert set(PACK_F_CHAOS_SCENARIOS) == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_scenario_passes_default_seed(name):
    report = run_pack_f_chaos(name)
    assert report.passed, (report.failed(), report.metrics)
    assert report.invariants


@pytest.mark.parametrize("seed", [1, 2, 3, 5, 8, 13, 21, 34])
def test_all_scenarios_pass_across_seeds(seed):
    failures = {r.name: r.failed() for r in run_all_pack_f_chaos(seed) if not r.passed}
    assert failures == {}


def test_scenarios_are_deterministic():
    a = [r.as_dict() for r in run_all_pack_f_chaos(4)]
    b = [r.as_dict() for r in run_all_pack_f_chaos(4)]
    assert a == b


def test_unknown_scenario():
    with pytest.raises(KeyError):
        run_pack_f_chaos("nope")


def test_retry_storm_amplification_metric():
    r = run_pack_f_chaos("retry_storm_bounded")
    assert r.metrics["upstream_calls"] < r.metrics["requests"] + r.metrics["naive_retries"] // 10


def test_report_semantics():
    r = ChaosReport("x", 0)
    assert not r.passed  # no invariants is not a pass
    r.check("a", True)
    assert r.passed
    r.check("b", False)
    assert not r.passed and r.failed() == ["b"]
    assert r.as_dict()["passed"] is False


class TestFaultyUpstream:
    def test_plan_validation(self):
        with pytest.raises(ValueError):
            FaultPlan(error_rate=1.5)
        with pytest.raises(ValueError):
            FaultPlan(outages=((5.0, 1.0),))

    def test_outage_windows(self):
        c = ManualClock()
        up = FaultyUpstream(c, FaultPlan(outages=((1.0, 2.0),)))
        req = PipelineRequest("GET", "/x")
        assert up(req, None).status == 200
        c.advance(1.5)
        assert up(req, None).status == 503
        c.advance(1.0)
        assert up(req, None).status == 200
        assert up.failures == 1 and up.calls == 3

    def test_latency_and_exceptions(self):
        c = ManualClock()
        up = FaultyUpstream(c, FaultPlan(latency_s=0.2, exception_rate=1.0))
        with pytest.raises(ConnectionError):
            up(PipelineRequest("GET", "/x"), None)
        assert c.monotonic() == pytest.approx(1000.2)

    def test_seeded_error_pattern_reproducible(self):
        def pattern(seed):
            c = ManualClock()
            up = FaultyUpstream(c, FaultPlan(error_rate=0.5), seed=seed)
            return [up(PipelineRequest("GET", "/x"), None).status for _ in range(30)]

        assert pattern(3) == pattern(3)
        assert pattern(3) != pattern(4)


class TestPackFPlane:
    def plane(self, pressure_state="open", load=0.1):
        clock = ManualClock()
        ring = KeyRing(clock=clock)
        ring.add_key("k1", b"s" * 32, activate=True)
        verifier = TokenVerifier("gateway", ring, clock=clock)
        view = {"schema_version": 1, "load": load, "queue_depth": 0, "max_queue_depth": 100,
                "tenant_queue_depth": None, "retry_after_s": 2.0 if pressure_state != "open" else 0.0,
                "state": pressure_state, "observed_at": iso_now(clock.now())}
        matrix = AdmissionMatrix(gate=AdaptiveGate(1000, 0), governor=ChaosGovernor(min_samples=1000))
        plane = build_pack_f_plane(
            verifier=verifier, pressure=StaticSource(view, name="pack_h"), matrix=matrix, clock=clock
        )
        signer = TokenSigner("forge-worker", ring, clock=clock)
        return plane, signer, clock

    def test_end_to_end_happy_path(self):
        plane, signer, clock = self.plane()
        tok = signer.mint("gateway", ["forge:read"])
        d = plane.s2s_gate.evaluate("GET", "/api/v1/forge/1", {"Authorization": f"Service {tok}"})
        assert d.allowed
        resp, ctx = plane.router.call(PipelineRequest("GET", "/api/v1/forge/1"), lambda r, c: PipelineResponse(200))
        assert resp.status == 200
        kinds = [s["kind"] for s in plane.router.pipeline_for(plane.router.resolve(PipelineRequest("GET", "/api/v1/x"))).describe()]
        assert kinds == ["telemetry", "backpressure", "deadline", "retry", "breaker", "attempt_timeout"]
        t = plane.telemetry
        assert t.counter(M_S2S_DECISIONS, outcome="allow", policy="forge-read", method="GET") == 1
        assert t.counter(M_PIPE_REQUESTS, route="s2s-read", method="GET", status_class="2xx") == 1
        assert len(t.spans(SPAN_PIPELINE)) == 1
        st = plane.status()
        assert st["s2s"] and "s2s-read" in st["routes"]

    def test_shed_under_pressure_end_to_end(self):
        plane, _signer, _clock = self.plane("shed", 0.99)
        calls = []
        resp, ctx = plane.router.call(
            PipelineRequest("GET", "/api/v1/forge/1"), lambda r, c: calls.append(1) or PipelineResponse(200)
        )
        assert resp.status == 429 and resp.header("retry-after") == "2"
        assert calls == []
        assert plane.status()["backpressure"] == {"shed:load_shed": 1}

    def test_breaker_transitions_reach_telemetry(self):
        plane, _signer, _clock = self.plane()
        rejected = 0
        for _ in range(10):
            try:
                plane.router.call(PipelineRequest("POST", "/api/v1/forge/1"), lambda r, c: PipelineResponse(503))
            except BreakerOpenError:
                rejected += 1
        assert rejected == 5  # default breaker trips after 5 consecutive failures
        assert plane.breakers.states().get("skeleton-api") == "open"
        gauges = plane.telemetry.snapshot()["gauges"]
        assert gauges["gate_plane.breaker.state{breaker=skeleton-api}"] == 2.0

    def test_without_verifier_no_s2s_gate(self):
        plane = build_pack_f_plane(clock=ManualClock(), pressure=StaticSource(lambda t: (_ for _ in ()).throw(KeyError())))
        assert plane.s2s_gate is None
        assert plane.status()["s2s"] is False
