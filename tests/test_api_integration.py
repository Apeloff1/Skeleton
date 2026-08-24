"""Integration tests: the API layer over the real wiring.

Hermetic — the app runs with the in-memory fallbacks (no ChromaDB, no
Mongo, no network), exactly as the architecture treatise prescribes.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skeleton.api import create_app


@pytest.fixture()
def client() -> TestClient:
    with TestClient(create_app()) as c:
        yield c


def test_root(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["version"] == "16.2.0"


def test_health_all_subsystems(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    for subsystem in ("kernel", "memory", "agents", "resilience",
                      "intelligence", "jeeves", "forge", "pipelines"):
        assert body["checks"][subsystem] is True


def test_capabilities_bootstrapped(client: TestClient) -> None:
    res = client.get("/api/v1/capabilities")
    assert res.status_code == 200
    names = {c["name"] for c in res.json()}
    assert {"npc", "game_logic", "animation", "universal"} <= names


def test_npc_pipeline_end_to_end(client: TestClient) -> None:
    res = client.post("/api/v1/pipeline/npc", json={
        "description": "a grizzled lighthouse keeper who trades in rumours",
        "name": "Maren",
        "dialogue_beats": 2,
    })
    assert res.status_code == 200
    npc = res.json()["npc"]
    assert npc["name"] == "Maren"
    assert npc["archetype"]
    assert len(npc["dialogue_tree"]) >= 3
    assert npc["behaviour_graph"]


def test_npc_pipeline_validation_error_maps_to_422(client: TestClient) -> None:
    res = client.post("/api/v1/pipeline/npc", json={"description": ""})
    assert res.status_code == 422
    assert res.json()["code"] == "PPL.VALIDATION"


def test_game_logic_pipeline(client: TestClient) -> None:
    res = client.post("/api/v1/pipeline/game-logic", json={
        "description": "arena battler with crafting",
        "title": "Arena",
        "curve": "linear",
    })
    assert res.status_code == 200
    logic = res.json()["game_logic"]
    assert logic["title"] == "Arena"
    assert logic["progression"]["curve"] == "linear"


def test_animation_pipeline(client: TestClient) -> None:
    res = client.post("/api/v1/pipeline/animation", json={
        "description": "humanoid knight",
        "actions": ["idle", "walk"],
    })
    assert res.status_code == 200
    anim = res.json()["animation"]
    assert {c["name"] for c in anim["clips"]} == {"idle", "walk"}
    assert anim["blend_tree"]["type"] == "blend_1d"


def test_jeeves_session_roundtrip(client: TestClient) -> None:
    res = client.post("/api/v1/jeeves/session", json={"user_id": "u1"})
    assert res.status_code == 200
    session_id = res.json()["session_id"]

    res = client.post("/api/v1/jeeves/interact", json={
        "session_id": session_id,
        "input": "How do I centre a div?",
    })
    assert res.status_code == 200
    assert res.json()["response"]

    res = client.post(f"/api/v1/jeeves/session/{session_id}/close")
    assert res.status_code == 200
    assert res.json()["status"] == "closed"


def test_jeeves_unknown_session_is_typed_error(client: TestClient) -> None:
    res = client.post("/api/v1/jeeves/interact", json={
        "session_id": "sess_nonexistent",
        "input": "hello",
    })
    assert res.status_code == 409
    assert res.json()["code"] == "JEE.SESSION"


def test_forge_blueprint_lifecycle(client: TestClient) -> None:
    res = client.post("/api/v1/forge/blueprint", json={
        "name": "quest-feed",
        "components": [
            {"kind": "source", "instance_id": "quests"},
            {"kind": "transform", "instance_id": "enrich"},
            {"kind": "sink", "instance_id": "ui"},
        ],
        "wires": [
            {"src": ["quests", "out"], "dst": ["enrich", "in"]},
            {"src": ["enrich", "out"], "dst": ["ui", "in"]},
        ],
    })
    assert res.status_code == 200
    blueprint_id = res.json()["blueprint_id"]

    res = client.post("/api/v1/forge/materialise", json={"blueprint_id": blueprint_id})
    assert res.status_code == 200
    artefact = res.json()["artefact"]
    assert artefact["execution_order"] == ["quests", "enrich", "ui"]


def test_forge_cycle_rejected(client: TestClient) -> None:
    res = client.post("/api/v1/forge/blueprint", json={
        "name": "loopy",
        "components": [
            {"kind": "transform", "instance_id": "a"},
            {"kind": "transform", "instance_id": "b"},
        ],
        "wires": [
            {"src": ["a", "out"], "dst": ["b", "in"]},
            {"src": ["b", "out"], "dst": ["a", "in"]},
        ],
    })
    blueprint_id = res.json()["blueprint_id"]
    res = client.post("/api/v1/forge/materialise", json={"blueprint_id": blueprint_id})
    assert res.status_code == 500
    assert res.json()["code"] == "FRG.MATERIALISE"


def test_swarm_join_route_stats(client: TestClient) -> None:
    res = client.post("/api/v1/swarm/agent", json={
        "specialisations": ["tutoring"],
    })
    assert res.status_code == 200

    res = client.post("/api/v1/swarm/route/tutoring")
    assert res.status_code == 200
    assert res.json()["agent_id"].startswith("agent_")

    res = client.get("/api/v1/swarm/stats")
    assert res.status_code == 200
    assert res.json()["agents"] >= 1


def test_memory_query_empty_store(client: TestClient) -> None:
    res = client.post("/api/v1/memory/query", json={"query": "anything"})
    assert res.status_code == 200
    assert res.json()["facts"] == []


def test_resilience_sanitise(client: TestClient) -> None:
    res = client.post("/api/v1/resilience/sanitise", json={
        "input": "perfectly ordinary question about python",
        "user_id": "u1",
    })
    assert res.status_code == 200
    assert "threat_level" in res.json()
