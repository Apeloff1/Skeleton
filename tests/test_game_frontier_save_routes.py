import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import game_frontier_authoring as gfa
from routes import game_frontier_authoring as r
from routes.gameforge_auth import get_current_user

EDITOR = {"email": "e@x", "tenant_id": "t1", "role": "editor"}
VIEWER = {"email": "e@x", "tenant_id": "t1", "role": "viewer"}
BASE = "/game-frontier-authoring/projects/p1"


@pytest.fixture
def client(monkeypatch, tmp_path):
    async def fake_source(scope, project_id):
        return {"version": 1}, {}
    monkeypatch.setattr(gfa, "_source", fake_source)
    monkeypatch.setenv(gfa.GAME_SAVE_DB_ENV, str(tmp_path / "gf.db"))
    gfa._reset_save_plane()
    app = FastAPI()
    app.include_router(r.router)
    user = {"u": EDITOR}
    app.dependency_overrides[get_current_user] = lambda: user["u"]
    c = TestClient(app)
    c.user = user
    yield c
    gfa._reset_save_plane()


def test_save_restore_paged(client):
    body = {"sequence": 1, "sections": {"weather": {"wind": 3}},
            "receipts": [{"chunk_id": f"c{i}", "body": {"i": i}} for i in range(5)]}
    res = client.post(f"{BASE}/saves/main", json=body)
    assert res.status_code == 200, res.text
    assert res.json()["receipt_root"]
    page = client.get(f"{BASE}/saves/main", params={"cursor": 2, "limit": 2}).json()
    assert page["sections"] == {"weather": {"wind": 3}}
    assert [x["body"]["i"] for x in page["receipts"]["items"]] == [2, 3]
    assert page["receipts"]["next_cursor"] == 4
    assert client.post(f"{BASE}/saves/main", json=body).status_code == 409
    assert client.get(f"{BASE}/saves/none").status_code == 409
    assert client.get(f"{BASE}/saves/main", params={"limit": 0}).status_code == 422


def test_viewer_cannot_write(client):
    client.user["u"] = VIEWER
    res = client.post(f"{BASE}/saves/main", json={"sequence": 1, "sections": {}})
    assert res.status_code == 403
    assert client.post(f"{BASE}/replays/r",
                       json={"frames": [{"frame": 0, "event": {}}]}).status_code == 403


def test_replay_routes(client):
    frames = [{"frame": f, "event": {"d": f}} for f in range(4)]
    assert client.post(f"{BASE}/replays/run", json={"frames": frames}).status_code == 200
    bad = client.post(f"{BASE}/replays/run",
                      json={"frames": [{"frame": 1, "event": {"d": 9}}]})
    assert bad.status_code == 409
    out = client.get(f"{BASE}/replays/run", params={"after": 0, "upto": 2}).json()
    assert [f["frame"] for f in out["frames"]] == [1, 2]
    assert client.post(f"{BASE}/replays/run", json={"extra": 1}).status_code == 422
