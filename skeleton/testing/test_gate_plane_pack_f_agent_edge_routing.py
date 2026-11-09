"""Agent edge — capability/lane routing, breaker-aware load balancing, swarm adapter."""

from __future__ import annotations

import pytest

from skeleton.gate_plane.agent_edge import (
    AgentEndpoint,
    AgentRegistry,
    AgentRouter,
    CallableSwarmDirectory,
    ModuleSwarmDirectory,
    RouteOutcome,
    RoutingError,
    StaticSwarmDirectory,
    SwarmRegistryAdapter,
)
from skeleton.gate_plane.agent_edge.routing import capability_matches
from skeleton.gate_plane.pipeline.breaker import BreakerConfig, BreakerRegistry, BreakerState
from skeleton.gate_plane.s2s.clock import ManualClock


@pytest.fixture
def clock():
    return ManualClock()


def ep(agent, lane="backend", caps=("plan.write",), **kw):
    return AgentEndpoint.build(agent, lane, caps, **kw)


def router(clock, *eps, **kw):
    br = BreakerRegistry(clock=clock, default=BreakerConfig(consecutive_failures=2, min_calls=2, window_size=4, cooldown_s=10))
    return AgentRouter(AgentRegistry(eps), breakers=br, clock=clock, **kw)


def test_capability_matching():
    assert capability_matches("plan.write", "plan.write")
    assert capability_matches("plan.*", "plan.write")
    assert not capability_matches("plan.*", "plan")
    assert not capability_matches("plan.write", "plan.read")


def test_endpoint_validation():
    with pytest.raises(RoutingError):
        ep("a1", caps=())
    with pytest.raises(RoutingError):
        ep("a1", caps=("Bad Cap",))
    with pytest.raises(RoutingError):
        ep("a1", lane="Bad Lane")
    with pytest.raises(RoutingError):
        ep("a1", capacity=0)


def test_route_by_capability_and_lane(clock):
    r = router(clock, ep("a1"), ep("a2", lane="frontend"), ep("a3", caps=("review.*",)))
    assert r.route("plan.write", lane="frontend").agent_id == "a2"
    assert r.route("review.code").agent_id == "a3"
    d = r.route("deploy.prod")
    assert d.outcome is RouteOutcome.NO_CANDIDATES and not d.routed
    with pytest.raises(RoutingError):
        r.route("BAD")


def test_least_loaded_wins_and_is_deterministic(clock):
    load = {"a1": 4, "a2": 1, "a3": 1}
    r = router(clock, ep("a1"), ep("a2"), ep("a3", weight=200), load_probe=lambda a: load[a])
    assert r.route("plan.write").agent_id == "a3"  # tie on load -> higher weight
    load["a3"] = 6
    assert r.route("plan.write").agent_id == "a2"


def test_capacity_normalises_load_and_saturation(clock):
    load = {"a1": 4, "a2": 3}
    r = router(clock, ep("a1", capacity=16), ep("a2", capacity=3), load_probe=lambda a: load[a])
    d = r.route("plan.write")
    assert d.agent_id == "a1" and d.excluded == {"a2": "saturated"}
    load["a1"] = 16
    d = r.route("plan.write")
    assert d.outcome is RouteOutcome.ALL_SATURATED and d.retry_after_s == 1.0


def test_in_flight_tracking_feeds_load(clock):
    r = router(clock, ep("a1", capacity=2), ep("a2", capacity=2))
    r.begin("a1")
    assert r.route("plan.write").agent_id == "a2"
    r.end("a1", ok=None)
    assert r.stats()["in_flight"] == {}


def test_breaker_open_excludes_agent_then_half_open_recovers(clock):
    r = router(clock, ep("a1"), ep("a2"))
    r.record("a1", ok=False)
    r.record("a1", ok=False)
    assert r.breaker("a1").state is BreakerState.OPEN
    d = r.route("plan.write")
    assert d.agent_id == "a2" and d.excluded["a1"] == "breaker_open"
    clock.advance(11)
    assert r.breaker("a1").state is BreakerState.HALF_OPEN
    r.record("a1", ok=True)
    assert r.breaker("a1").state is BreakerState.CLOSED
    assert "agent:a1" in r.stats()["breakers"]


def test_all_breakers_open_reports_retry_after(clock):
    r = router(clock, ep("a1"))
    r.record("a1", ok=False)
    r.record("a1", ok=False)
    clock.advance(4)
    d = r.route("plan.write")
    assert d.outcome is RouteOutcome.ALL_BREAKERS_OPEN
    assert d.retry_after_s == pytest.approx(6.0, abs=0.05)


def test_draining_and_disabled_excluded(clock):
    r = router(clock, ep("a1"), ep("a2"))
    r.registry.set_draining("a1")
    r.registry.set_enabled("a2", False)
    d = r.route("plan.write")
    assert d.outcome is RouteOutcome.ALL_UNAVAILABLE
    assert d.excluded == {"a1": "draining", "a2": "disabled"}
    with pytest.raises(KeyError):
        r.registry.set_draining("zz")


def test_conversation_affinity_sticks_until_ineligible(clock):
    load = {"a1": 0, "a2": 0}
    r = router(clock, ep("a1"), ep("a2"), load_probe=lambda a: load[a])
    first = r.route("plan.write", conversation_id="conv-1").agent_id
    load[first] = 5
    d = r.route("plan.write", conversation_id="conv-1")
    assert d.agent_id == first and d.outcome is RouteOutcome.AFFINITY
    r.registry.set_draining(first)
    moved = r.route("plan.write", conversation_id="conv-1")
    assert moved.agent_id != first and moved.outcome is RouteOutcome.ROUTED
    assert r.affinity_of("conv-1") == moved.agent_id
    r.forget_conversation("conv-1")
    assert r.affinity_of("conv-1") is None


def test_affinity_bounded(clock):
    r = router(clock, ep("a1"), affinity_capacity=2)
    for i in range(5):
        r.route("plan.write", conversation_id=f"c-{i}")
    assert r.stats()["affinity_entries"] == 2


def test_route_direct(clock):
    r = router(clock, ep("a1"))
    assert r.route_direct("a1").outcome is RouteOutcome.DIRECT
    assert r.route_direct("zz").outcome is RouteOutcome.NO_CANDIDATES
    r.record("a1", ok=False)
    r.record("a1", ok=False)
    assert r.route_direct("a1").outcome is RouteOutcome.ALL_BREAKERS_OPEN
    r.registry.set_enabled("a1", False)
    assert r.route_direct("a1").outcome is RouteOutcome.ALL_UNAVAILABLE


def test_broken_load_probe_is_not_fatal(clock):
    r = router(clock, ep("a1"), load_probe=lambda a: 1 / 0)
    assert r.route("plan.write").agent_id == "a1"


# -- swarm adapter -----------------------------------------------------------------------
def test_swarm_adapter_projects_and_syncs():
    reg = AgentRegistry([ep("manual", caps=("ops.run",))])
    data = {
        "agents": [
            {"id": "Planner One", "role": "Internal Systems", "capabilities": ["plan.write", "plan.read"]},
            {"agent_id": "reviewer", "lane": "qa", "capabilities": {"review.*": True, "off": False}, "capacity": 3},
            {"agent_id": "broken", "capabilities": []},
        ]
    }
    directory = StaticSwarmDirectory(data)
    ad = SwarmRegistryAdapter(directory, reg)
    rep = ad.sync()
    assert set(rep.added) == {"planner-one", "reviewer"} and "broken" in rep.skipped
    assert reg.get("planner-one").lane == "internal-systems"
    assert reg.get("reviewer").capabilities == frozenset({"review.*"})
    data["agents"] = data["agents"][1:2]
    rep = ad.sync()
    assert rep.removed == ("planner-one",) and "manual" in reg
    assert ad.last_report is rep and rep.ok


def test_swarm_adapter_keyed_shape_and_outage():
    reg = AgentRegistry()
    ad = SwarmRegistryAdapter(CallableSwarmDirectory(lambda: {"worker-1": {"lane": "swarm", "capabilities": ["work.item"]}}), reg)
    assert ad.sync().added == ("worker-1",)

    def boom():
        raise RuntimeError("swarm down")

    bad = SwarmRegistryAdapter(CallableSwarmDirectory(boom), reg)
    rep = bad.sync()
    assert not rep.ok and "swarm down" in rep.error and "worker-1" in reg


def test_module_directory_reads_internal_systems_capabilities():
    snap = ModuleSwarmDirectory().snapshot()
    assert isinstance(snap, dict)
    rep = SwarmRegistryAdapter(ModuleSwarmDirectory(), AgentRegistry()).sync()
    assert rep.ok
