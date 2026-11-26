"""Regression coverage for the July/August CNS activation recovery."""
from __future__ import annotations

import pytest

from gameforge.bootstrap import begin_cns_activation as activation
from gameforge.bootstrap.full_room_agent_bootstrap import FullRoomAgentBootstrap


def room(rid="research", seats=8):
    return {"room_id": rid, "category": "research", "role": "analyst", "seats": seats}


def agent(aid="a1", rid="research", seat=None):
    return {"agent_id": aid, "room_id": rid, "seat_id": seat}


def test_registry_materializes_every_declared_room():
    engine = activation.BeginCNSActivation()
    report = engine.run()
    registry = activation.all_rooms()
    assert report["rooms"] == len(registry) == 1000
    assert report["agents"] == report["bindings"] == len(registry)
    assert report["rooms_without_agents"] == 0
    assert report["overall_status"] == "TOPOLOGY_READY"
    assert report["runtime_qualified"] is False
    assert report["rag"] == report["orchestrator"] == "unqualified"
    inventory = engine.inventory()
    assert {r["room_id"] for r in inventory["room_inventory"]} == set(registry)
    for a in inventory["agent_inventory"]:
        assert a["role_id"] == registry[a["room_id"]]["role"]


def test_deterministic_idempotence_and_real_seats():
    engine = FullRoomAgentBootstrap()
    manifest = [room("research", 2), room("world", 1)]
    assignments = [agent("a2"), agent("a1", seat="research_seat_0"), agent("a3", "world")]
    first = engine.bootstrap(manifest, assignments)
    second = engine.bootstrap(list(reversed(manifest)), list(reversed(assignments)))
    assert first["topology_sha256"] == second["topology_sha256"]
    assert first["generation"] == second["generation"] == 1
    assert {a["seat_id"] for a in engine.snapshot()["agent_inventory"]} == {
        "research_seat_0", "research_seat_1", "world_seat_0"
    }


@pytest.mark.parametrize(("manifest", "assignments"), [
    ([room(), room()], []),
    ([room()], [agent(rid="missing")]),
    ([room()], [agent(), agent()]),
    ([room()], [agent(seat="other_seat_0")]),
    ([room()], [agent("a1", seat="research_seat_0"), agent("a2", seat="research_seat_0")]),
    ([room(seats=1)], [agent("a1"), agent("a2")]),
    ([room(seats=True)], []),
    ([room(seats=65)], []),
    ([room("../escape")], []),
    ([{"room_id": "r", "category": "a b"}], []),
    ([None], []),
])
def test_invalid_generation_never_replaces_snapshot(manifest, assignments):
    engine = FullRoomAgentBootstrap()
    engine.bootstrap([room()], [agent()])
    before = engine.snapshot()
    with pytest.raises(ValueError):
        engine.bootstrap(manifest, assignments)
    assert engine.snapshot() == before


def test_snapshot_is_detached_and_empty_is_not_ready():
    engine = FullRoomAgentBootstrap()
    assert engine.bootstrap([], [])["overall_status"] == "EMPTY_MANIFEST"
    engine.bootstrap([room()], [])
    snapshot = engine.snapshot()
    snapshot["agent_inventory"][0]["room_id"] = "forged"
    assert engine.snapshot()["agent_inventory"][0]["room_id"] == "research"


def test_failed_registry_reactivation_does_not_claim_live(monkeypatch):
    engine = activation.BeginCNSActivation()
    assert engine.status_report()["overall_status"] == "NOT_ACTIVATED"
    monkeypatch.setattr(activation, "all_rooms", lambda: {"r": {"role": "analyst"}})
    first = engine.run()
    monkeypatch.setattr(activation, "all_rooms", lambda: {"invalid room": {"role": "analyst"}})
    second = engine.run()
    assert second["overall_status"] == "DEGRADED"
    assert second["runtime_qualified"] is False
    assert second["topology_sha256"] == first["topology_sha256"]
    assert second["errors"] == ["registry_topology_invalid"]


@pytest.mark.asyncio
async def test_http_activation_reports_only_topology(monkeypatch):
    from routes.gameforge_cns import gameforge_activate, gameforge_activation_status
    engine = activation.BeginCNSActivation()
    monkeypatch.setattr(activation, "get_activation", lambda: engine)
    monkeypatch.setattr(activation, "all_rooms", lambda: {"r": {"role": "analyst"}})
    assert (await gameforge_activation_status())["overall_status"] == "NOT_ACTIVATED"
    result = await gameforge_activate()
    assert result["status"] == "topology_ready"
    assert result["runtime_qualified"] is False
    assert (await gameforge_activation_status())["generation"] == 1
