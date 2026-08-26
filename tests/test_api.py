"""Tests for the HTTP interface layer (app factory, health, end-to-end)."""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from skeleton.api.server import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


class TestSurface:
    def test_root(self, client):
        assert client.get("/").json()["status"] == "operational"

    def test_health(self, client):
        body = client.get("/health").json()
        assert body["status"] == "healthy"
        assert body["checks"]["overall"] is True
        assert body["checks"]["genesis"] is True

    def test_live_ready(self, client):
        assert client.get("/health/live").json()["status"] in {"up", "down"}
        assert client.get("/health/ready").json()["status"] in {"up", "down"}

    def test_metrics(self, client):
        assert "counters" in client.get("/metrics").json()

    def test_genesis(self, client):
        body = client.get("/api/v1/genesis").json()
        assert "kernel" in body["report"]["phases"]
        assert body["health"]["subsystems"] >= 20

    def test_capabilities(self, client):
        names = {c["name"] for c in client.get("/api/v1/capabilities").json()}
        assert {"npc", "game_logic", "animation"} <= names

    def test_npc_pipeline_e2e(self, client):
        res = client.post("/api/v1/pipeline/npc", json={"description": "a weary ferryman"})
        assert res.status_code == 200
        assert res.json()["npc"]["archetype"]

    def test_jeeves_e2e(self, client):
        sess = client.post("/api/v1/jeeves/session", json={"user_id": "u1"}).json()
        res = client.post(
            "/api/v1/jeeves/interact",
            json={"session_id": sess["session_id"], "input": "What is a hash map?"},
        )
        assert res.status_code == 200
        assert res.json()["response"]

    def test_validation_error_maps_to_422(self, client):
        res = client.post("/api/v1/pipeline/npc", json={"description": ""})
        assert res.status_code == 422
        assert res.json()["code"] == "PPL.VALIDATION"

    def test_forge_e2e(self, client):
        res = client.post("/api/v1/forge/materialise", json={
            "name": "pipe",
            "components": [
                {"kind": "source", "instance_id": "a"},
                {"kind": "sink", "instance_id": "b"},
            ],
            "wires": [{"from": ["a", "out"], "to": ["b", "in"]}],
        })
        assert res.status_code == 200
        assert res.json()["artefact"]["execution_order"] == ["a", "b"]

    def test_swarm_join(self, client):
        res = client.post("/api/v1/swarm/agent", json={"specialisations": ["npc"]})
        assert res.status_code == 200
        assert client.get("/api/v1/swarm/stats").json()["agents"] >= 1
