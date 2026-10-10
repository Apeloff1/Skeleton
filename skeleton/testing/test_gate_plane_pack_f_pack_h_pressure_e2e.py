"""Pack F x Pack H — real admit pressure driving the gate-plane backpressure adapter end to end.

Wires Backend's real ``skeleton.api.pack_h.admit_pressure`` board (in-process
source, no fakes on the Pack H side) through the registry into the
``default_backpressure_gate`` FallbackChain, then exercises it through:

* the s2s ``PipelineRouter`` (route pipelines with a backpressure stage),
* the hardened gate in front of it (request-id survives into the pipeline),
* the egress gateway (shed callbacks are rescheduled, never sent).
"""

from __future__ import annotations

import random

import pytest

from skeleton.api.pack_h import admit_pressure as ap
from skeleton.gate_plane.admit import AdmissionMatrix
from skeleton.gate_plane.backpressure import (
    BackpressureGate,
    PackHSource,
    backpressure_stage_factory,
    default_backpressure_gate,
    register_adaptive_gate,
    register_pressure_provider,
    reset_registry_for_tests,
)
from skeleton.gate_plane.backpressure.gate import BackpressureStage
from skeleton.gate_plane.egress import (
    Callback,
    DeliveryOutcome,
    EgressAllowlist,
    EgressGateway,
    ScriptedTransport,
    SecretSet,
    Subscription,
    encode_secret,
)
from skeleton.gate_plane.hardening import RequestIdStage, bind_context, build_hardened_gate
from skeleton.gate_plane.pipeline.core import PipelineRequest, PipelineResponse
from skeleton.gate_plane.pipeline.retry import RetrySpec
from skeleton.gate_plane.pipeline.routes import PipelineRouter, RouteConfig, RouteTable
from skeleton.gate_plane.s2s.authz import default_gate_plane_policies
from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.tokens import TokenSigner, TokenVerifier
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor


class FakeMono:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        self.t += 0.001  # strictly increasing so the board's TTL cache never pins a stale view
        return self.t


@pytest.fixture
def board():
    mono = FakeMono()
    drain = ap.DrainMeter(half_life_s=10.0, clock=mono)
    source = ap.InProcessPressureSource(max_concurrency=4, max_queue_depth=10, max_tenant_queue_depth=3, drain=drain)
    b = ap.PressureBoard(source, ttl_s=0.0, clock=mono)
    ap.install_board(b)
    reset_registry_for_tests()
    register_pressure_provider(ap.snapshot)  # the real Backend module-level helper
    try:
        yield source
    finally:
        reset_registry_for_tests()
        ap.install_board(None)


@pytest.fixture
def clock():
    return ManualClock()


def router(clock, gate=None):
    gate = gate or default_backpressure_gate()
    table = RouteTable([
        RouteConfig("swarm", "/api/v1/swarm/**", upstream="swarm", timeout_s=5.0,
                    retry=RetrySpec(max_attempts=2, base_backoff_s=0.01, jitter=0)),
    ])
    return PipelineRouter(
        table, clock=clock, rng=random.Random(0),
        stage_factories={"telemetry": lambda r: RequestIdStage(service="gateway"),
                         "backpressure": backpressure_stage_factory(gate)},
    )


def ok_handler(calls):
    def handler(req, ctx):
        calls.append(req)
        return PipelineResponse(200, {"ok": True})

    return handler


def fill(source, n, tenant="t-bulk"):
    for _ in range(n):
        source.enqueue(tenant)


def test_contract_reaches_adapter_as_pack_h(board):
    view = PackHSource().read(None)
    assert view.source == "pack_h" and view.schema_version == 1 and view.effective_state.value == "open"


def test_open_pressure_admits_and_reports_source(board, clock):
    calls = []
    resp, ctx = router(clock).call(PipelineRequest("GET", "/api/v1/swarm/jobs"), ok_handler(calls))
    assert resp.status == 200 and len(calls) == 1
    assert ctx.attrs["backpressure"]["source"] == "pack_h" and ctx.attrs["backpressure"]["action"] == "admit"
    assert ctx.event_names()[0] == "request_id"


def test_throttle_with_long_wait_sheds_429(board, clock):
    fill(board, 8)  # load 0.8, no drain rate -> retry_after (0.1/0.3)*30 = 10s
    calls = []
    resp, ctx = router(clock).call(PipelineRequest("POST", "/api/v1/swarm/jobs"), ok_handler(calls))
    assert resp.status == 429 and calls == []
    assert resp.header("retry-after") == "10" and resp.body["retry_after_s"] == 10.0
    assert ctx.attrs["backpressure"]["reason"] == "throttle_wait_too_long"


def test_throttle_with_fast_drain_delays_then_admits(board, clock):
    fill(board, 8)
    board.drain.record(200)  # ~13.9 completions/s -> excess 1 / rate ~ 0.07s
    calls = []
    resp, ctx = router(clock).call(PipelineRequest("GET", "/api/v1/swarm/jobs"), ok_handler(calls))
    assert resp.status == 200 and len(calls) == 1
    assert ctx.attrs["backpressure"]["action"] == "delay"
    assert clock.sleeps and 0 < clock.sleeps[0] <= 0.25


def test_queue_full_sheds_503(board, clock):
    fill(board, 10)
    resp, ctx = router(clock).call(PipelineRequest("POST", "/api/v1/swarm/jobs"), ok_handler([]))
    assert resp.status == 503 and resp.body["error"] == "overloaded"
    assert ctx.attrs["backpressure"]["reason"] == "queue_full"


def test_tenant_queue_isolation(board, clock):
    fill(board, 3, tenant="noisy")  # noisy tenant at its own cap, global load still low
    r = router(clock)
    noisy, _ = r.call(PipelineRequest("POST", "/api/v1/swarm/jobs", tenant_id="noisy"), ok_handler([]))
    quiet, _ = r.call(PipelineRequest("POST", "/api/v1/swarm/jobs", tenant_id="quiet"), ok_handler([]))
    assert noisy.status == 429 and quiet.status == 200


def test_control_priority_admitted_under_shed(board, clock):
    fill(board, 10)
    resp, ctx = router(clock).call(PipelineRequest("GET", "/api/v1/swarm/health", priority=0), ok_handler([]))
    assert resp.status == 200 and ctx.attrs["backpressure"]["reason"].endswith("_control_exempt")


def test_recovery_after_drain(board, clock):
    fill(board, 10, tenant="t")
    r = router(clock)
    assert r.call(PipelineRequest("GET", "/api/v1/swarm/x"), ok_handler([]))[0].status == 503
    for _ in range(10):
        board.abandon("t")
    assert r.call(PipelineRequest("GET", "/api/v1/swarm/x"), ok_handler([]))[0].status == 200


def test_shed_never_spends_retry_budget(board, clock):
    fill(board, 10)
    r = router(clock)
    for _ in range(5):
        r.call(PipelineRequest("GET", "/api/v1/swarm/x"), ok_handler([]))
    assert r.budgets.stats().get("swarm", {}).get("withdrawals", 0) == 0


def test_fallback_to_adaptive_gate_when_pack_h_unregistered(board, clock):
    register_pressure_provider(None)
    adaptive = AdaptiveGate(2, 0)
    register_adaptive_gate(adaptive)
    r = router(clock)
    resp, ctx = r.call(PipelineRequest("GET", "/api/v1/swarm/x"), ok_handler([]))
    assert resp.status == 200 and ctx.attrs["backpressure"]["source"] == "adaptive_gate"
    adaptive.admit(1)
    adaptive.admit(1)
    resp2, ctx2 = r.call(PipelineRequest("GET", "/api/v1/swarm/x"), ok_handler([]))
    assert resp2.status in (429, 503) and ctx2.attrs["backpressure"]["source"] == "adaptive_gate"


def test_no_signal_admits_by_default_and_sheds_when_configured(board, clock):
    reset_registry_for_tests()
    resp, ctx = router(clock).call(PipelineRequest("GET", "/api/v1/swarm/x"), ok_handler([]))
    assert resp.status == 200 and ctx.attrs["backpressure"]["reason"] == "no_signal"
    strict = default_backpressure_gate(on_no_signal="shed")
    resp2, _ = router(clock, strict).call(PipelineRequest("GET", "/api/v1/swarm/x"), ok_handler([]))
    assert resp2.status == 503


def test_board_source_failure_fails_closed(board, clock):
    class Broken:
        max_queue_depth = 10

        def observe(self, tenant_id=None):
            raise ap.PressureSourceError("ledger down")

    ap.install_board(ap.PressureBoard(Broken(), ttl_s=0.0))
    resp, ctx = router(clock).call(PipelineRequest("GET", "/api/v1/swarm/x"), ok_handler([]))
    assert resp.status in (429, 503) and ctx.attrs["backpressure"]["action"] == "shed"


def test_hardened_gate_then_pressure_pipeline_shares_request_id(board, clock):
    ring = KeyRing(clock=clock)
    ring.add_key("forge:1", b"F" * 32, activate=True)
    gate = build_hardened_gate(
        TokenVerifier("gateway", ring, clock=clock), default_gate_plane_policies(), service="gateway",
        matrix=AdmissionMatrix(gate=AdaptiveGate(100, 0), governor=ChaosGovernor(min_samples=1000)),
    )
    tok = TokenSigner("forge", ring, clock=clock).mint("gateway", ["swarm:read"])
    decision = gate.evaluate("GET", "/api/v1/swarm/jobs", {"Authorization": f"Service {tok}",
                                                            "x-request-id": "req-e2epressure01"})
    assert decision.allowed
    calls = []
    with bind_context(decision.context):
        resp, _ = router(clock).call(PipelineRequest("GET", "/api/v1/swarm/jobs", service="gateway"), ok_handler(calls))
    assert resp.status == 200 and calls[0].headers["x-request-id"] == "req-e2epressure01"
    assert calls[0].headers["x-s2s-hop"] == "1"


def test_egress_callbacks_rescheduled_under_pressure(board, clock):
    allow = EgressAllowlist(["hooks.example.com"], resolver=lambda h: ["93.184.216.34"])
    tr = ScriptedTransport()
    stage = BackpressureStage(BackpressureGate(default_backpressure_gate().source))
    gw = EgressGateway(allow, tr, clock=clock, backpressure_stage=stage, redelivery_jitter=0.0, rng=random.Random(1))
    gw.register(Subscription("sub-a", "https://hooks.example.com/cb", SecretSet.of(encode_secret(b"k" * 32))))
    fill(board, 10)
    res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_pressure"))
    assert res.outcome is DeliveryOutcome.SCHEDULED and res.status == 503 and tr.requests == []
    for _ in range(10):
        board.abandon("t-bulk")
    clock.advance(30)
    (res2,) = gw.drain()
    assert res2.delivered and len(tr.requests) == 1
