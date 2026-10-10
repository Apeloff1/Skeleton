"""Pack F mesh-lite — peer health probes, outlier ejection, sticky routing, mesh client."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from skeleton.gate_plane.mesh import (
    Endpoint,
    HealthConfig,
    MeshClient,
    NoEndpointAvailable,
    PeerSet,
    PeerState,
    Selector,
    rendezvous_rank,
)
from skeleton.gate_plane.pipeline.budget import RetryBudget
from skeleton.gate_plane.pipeline.core import Pipeline, PipelineRequest, PipelineResponse
from skeleton.gate_plane.pipeline.errors import AttemptTimeout
from skeleton.gate_plane.pipeline.retry import RetrySpec
from skeleton.gate_plane.pipeline.stages import DeadlineStage, RetryStage
from skeleton.gate_plane.s2s.clock import ManualClock


@pytest.fixture
def clock():
    return ManualClock()


def peers(clock, n=3, **cfg):
    eps = [Endpoint(f"ep{i}", f"10.0.0.{i}:8000", zone="a" if i % 2 == 0 else "b") for i in range(n)]
    return PeerSet("swarm", eps, config=HealthConfig(**cfg) if cfg else None, clock=clock)


class TestEndpointAndConfig:
    @pytest.mark.parametrize("kw", [{"id": "bad id", "address": "x"}, {"id": "a", "address": ""},
                                    {"id": "a", "address": "x", "weight": 0}])
    def test_endpoint_validation(self, kw):
        with pytest.raises(ValueError):
            Endpoint(**kw)

    @pytest.mark.parametrize("kw", [{"unhealthy_threshold": 0}, {"base_ejection_s": 0},
                                    {"base_ejection_s": 10, "max_ejection_s": 5}, {"max_ejection_percent": 2}])
    def test_config_validation(self, kw):
        with pytest.raises(ValueError):
            HealthConfig(**kw)

    def test_membership(self, clock):
        ps = peers(clock)
        with pytest.raises(ValueError):
            ps.add(Endpoint("ep0", "x"))
        ps.remove("ep0")
        assert len(ps) == 2 and ps.get("ep0") is None and ps.state_of("ep0") is None


class TestHealth:
    def test_probe_thresholds(self, clock):
        ps = peers(clock, unhealthy_threshold=2, healthy_threshold=2)
        transitions = []
        ps.add_listener(lambda svc, ep, a, b: transitions.append((ep, a, b)))
        ps.add_listener(lambda *a: 1 / 0)
        ps.probe_all(lambda ep: ep.id != "ep1")
        assert ps.state_of("ep1") is PeerState.HEALTHY
        ps.probe_all(lambda ep: ep.id != "ep1")
        assert ps.state_of("ep1") is PeerState.UNHEALTHY
        ps.probe_all(lambda ep: True)
        assert ps.state_of("ep1") is PeerState.UNHEALTHY
        ps.probe_all(lambda ep: True)
        assert ps.state_of("ep1") is PeerState.HEALTHY
        assert transitions == [("ep1", PeerState.HEALTHY, PeerState.UNHEALTHY),
                               ("ep1", PeerState.UNHEALTHY, PeerState.HEALTHY)]

    def test_crashing_probe_counts_as_failure(self, clock):
        ps = peers(clock, unhealthy_threshold=1)

        def probe(ep):
            raise RuntimeError("down")

        assert ps.probe_all(probe) == {"ep0": False, "ep1": False, "ep2": False}
        assert all(ps.state_of(f"ep{i}") is PeerState.UNHEALTHY for i in range(3))

    def test_outlier_ejection_with_backoff(self, clock):
        ps = peers(clock, n=4, consecutive_failures=3, base_ejection_s=10, max_ejection_s=25)
        for _ in range(3):
            ps.record_result("ep0", False)
        assert ps.state_of("ep0") is PeerState.EJECTED
        clock.advance(10)
        assert ps.state_of("ep0") is PeerState.HEALTHY
        for _ in range(3):
            ps.record_result("ep0", False)
        assert ps.get("ep0").ejected_until == pytest.approx(clock.monotonic() + 20)
        clock.advance(20)
        for _ in range(3):
            ps.record_result("ep0", False)
        assert ps.get("ep0").ejected_until == pytest.approx(clock.monotonic() + 25)

    def test_success_resets_streak(self, clock):
        ps = peers(clock, consecutive_failures=2)
        ps.record_result("ep0", False)
        ps.record_result("ep0", True)
        ps.record_result("ep0", False)
        assert ps.state_of("ep0") is PeerState.HEALTHY

    def test_max_ejection_percent(self, clock):
        ps = peers(clock, n=4, consecutive_failures=1, max_ejection_percent=0.5)
        for i in range(4):
            ps.record_result(f"ep{i}", False)
        states = Counter(ps.state_of(f"ep{i}") for i in range(4))
        assert states[PeerState.EJECTED] == 2 and states[PeerState.HEALTHY] == 2

    def test_draining_and_panic_mode(self, clock):
        ps = peers(clock, n=2, unhealthy_threshold=1)
        ps.drain("ep0")
        assert ps.state_of("ep0") is PeerState.DRAINING
        assert [h.endpoint.id for h in ps.available()] == ["ep1"]
        ps.record_probe("ep1", False)
        # all non-draining peers unhealthy -> panic: still offer ep1, never the draining one
        assert [h.endpoint.id for h in ps.available()] == ["ep1"]
        ps.drain("ep0", False)
        assert len(ps.available()) == 1 and ps.available()[0].endpoint.id == "ep0"

    def test_in_flight_and_snapshot(self, clock):
        ps = peers(clock)
        ps.acquire("ep0")
        ps.acquire("ep0")
        ps.release("ep0")
        ps.release("ep0")
        ps.release("ep0")
        snap = {s["id"]: s for s in ps.snapshot()}
        assert snap["ep0"]["in_flight"] == 0 and snap["ep0"]["state"] == "healthy"


class TestSelection:
    def test_rendezvous_stable_and_minimal_remap(self, clock):
        ps = peers(clock, n=5)
        sel = Selector(ps)
        keys = [f"tenant-{i}" for i in range(400)]
        before = {k: sel.pick(sticky_key=k).id for k in keys}
        assert before == {k: sel.pick(sticky_key=k).id for k in keys}
        assert len(set(before.values())) == 5
        ps.remove("ep2")
        after = {k: sel.pick(sticky_key=k).id for k in keys}
        moved = [k for k in keys if before[k] != after[k]]
        assert moved and all(before[k] == "ep2" for k in moved)

    def test_sticky_failover_and_return(self, clock):
        ps = peers(clock, n=3, consecutive_failures=1, base_ejection_s=5)
        sel = Selector(ps)
        home = sel.pick(sticky_key="conv-42").id
        second = rendezvous_rank("conv-42", [ps.get(f"ep{i}") for i in range(3)])[1].endpoint.id
        ps.record_result(home, False)
        assert sel.pick(sticky_key="conv-42").id == second
        clock.advance(5)
        assert sel.pick(sticky_key="conv-42").id == home

    def test_weights_bias_rendezvous(self, clock):
        ps = PeerSet("s", [Endpoint("heavy", "a", weight=9.0), Endpoint("light", "b", weight=1.0)], clock=clock)
        sel = Selector(ps)
        counts = Counter(sel.pick(sticky_key=f"k{i}").id for i in range(2000))
        assert counts["heavy"] > counts["light"] * 4

    def test_p2c_prefers_less_loaded(self, clock):
        ps = peers(clock, n=2)
        for _ in range(5):
            ps.acquire("ep0")
        sel = Selector(ps, rng=random.Random(1))
        assert all(sel.pick().id == "ep1" for _ in range(20))

    def test_zone_preference_and_exclude(self, clock):
        ps = peers(clock, n=4)
        sel = Selector(ps, local_zone="b", rng=random.Random(3))
        assert {sel.pick().id for _ in range(30)} <= {"ep1", "ep3"}
        assert sel.pick(exclude={"ep1", "ep3"}).id in {"ep0", "ep2"}
        assert sel.pick(exclude={"ep0", "ep1", "ep2", "ep3"}) is None

    def test_single_candidate(self, clock):
        ps = peers(clock, n=1)
        assert Selector(ps).pick().id == "ep0"


class TestMeshClient:
    def _client(self, clock, ps, send, attempts=3):
        spec = RetrySpec(max_attempts=attempts, base_backoff_s=0.01, max_backoff_s=0.05, jitter=0)
        pipe = Pipeline([DeadlineStage(5.0), RetryStage(spec, budget=RetryBudget(clock=clock))], clock=clock)
        return MeshClient(ps, pipe, send, spec=spec, selector=Selector(ps, rng=random.Random(0)))

    def test_retry_goes_to_a_different_peer(self, clock):
        ps = peers(clock)
        calls = []

        def send(ep, req, ctx):
            calls.append(ep.id)
            return PipelineResponse(503 if len(calls) == 1 else 200)

        client = self._client(clock, ps, send)
        ctx = client.pipeline.new_context()
        resp = client.call(PipelineRequest("GET", "/x"), sticky_key="t1", ctx=ctx)
        assert resp.status == 200 and len(calls) == 2 and calls[0] != calls[1]
        assert ctx.attrs["endpoints"] == calls
        assert ps.get(calls[0]).failures == 1 and ps.get(calls[1]).successes == 1

    def test_transport_errors_feed_ejection(self, clock):
        ps = peers(clock, n=2, consecutive_failures=1, max_ejection_percent=1.0)
        bad = {"ep0"}

        def send(ep, req, ctx):
            if ep.id in bad:
                raise ConnectionError("refused")
            return PipelineResponse(200)

        client = self._client(clock, ps, send)
        for i in range(10):
            assert client.call(PipelineRequest("GET", "/x"), sticky_key=f"k{i}").status == 200
        assert ps.state_of("ep0") is PeerState.EJECTED

    def test_attempt_timeout_counts_as_failure(self, clock):
        ps = peers(clock, n=1)

        def send(ep, req, ctx):
            raise AttemptTimeout("slow")

        with pytest.raises(AttemptTimeout):
            self._client(clock, ps, send).call(PipelineRequest("GET", "/x"))
        assert ps.get("ep0").failures == 3 and ps.get("ep0").in_flight == 0

    def test_all_peers_tried_allows_repeat(self, clock):
        ps = peers(clock, n=1)
        calls = []

        def send(ep, req, ctx):
            calls.append(ep.id)
            return PipelineResponse(503)

        resp = self._client(clock, ps, send).call(PipelineRequest("GET", "/x"))
        assert resp.status == 503 and calls == ["ep0", "ep0", "ep0"]

    def test_no_endpoints(self, clock):
        ps = PeerSet("empty", clock=clock)
        with pytest.raises(NoEndpointAvailable):
            self._client(clock, ps, lambda *a: PipelineResponse(200)).call(PipelineRequest("GET", "/x"))

    def test_sticky_key_from_header_or_tenant(self, clock):
        assert MeshClient.sticky_key_for(PipelineRequest("GET", "/", headers={"X-S2S-Sticky": " s1 "})) == "s1"
        assert MeshClient.sticky_key_for(PipelineRequest("GET", "/", tenant_id="t7")) == "t7"
        assert MeshClient.sticky_key_for(PipelineRequest("GET", "/")) is None

    def test_client_error_is_not_a_peer_failure(self, clock):
        ps = peers(clock, n=1, consecutive_failures=1)
        resp = self._client(clock, ps, lambda ep, r, c: PipelineResponse(404)).call(PipelineRequest("GET", "/x"))
        assert resp.status == 404 and ps.state_of("ep0") is PeerState.HEALTHY and ps.get("ep0").successes == 1
