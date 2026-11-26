"""Hermetic HTTP admission and scoped publication tests for the recovered polish API."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from core.forge_quality_contract import artifact_text, source_digest


def test_bounded_route_replays_exact_admitted_bytes():
    from routes.quality_polish_api import _BoundedPolishRoute, _MAX_WIRE_BYTES

    router = APIRouter(route_class=_BoundedPolishRoute)

    @router.post("/probe")
    async def probe(request: Request):
        body = await request.body()
        return {"length": len(body), "text": body.decode()}

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        source = b'{"content":{"x":1}}'
        result = client.post("/probe", content=source)
        assert result.status_code == 200
        assert result.json() == {"length": len(source), "text": source.decode()}
        too_large = client.post("/probe", content=b"x" * (_MAX_WIRE_BYTES + 1))
        assert too_large.status_code == 413
        assert "no-store" in too_large.headers["cache-control"]
        assert client.post("/probe", content=b'{"x":1,"x":2}').status_code == 400
        assert client.post("/probe", content=source, headers={"Content-Encoding": "gzip"}).status_code == 415


def test_router_declared_and_mounted():
    from core.routes_registry import KNOWN_ROUTES
    from routes.quality_polish_api import router

    assert ("routes.quality_polish_api", "router") in KNOWN_ROUTES
    assert {route.path for route in router.routes} == {
        "/api/polish/artifact", "/api/polish/{pid}/stage/{stage}",
    }
    assert all(route.dependencies for route in router.routes)


class Collection:
    def __init__(self, original, *, conflict=False):
        self.original = original
        self.conflict = conflict
        self.reads = []
        self.writes = []

    async def find_one(self, query, projection):
        self.reads.append((query, projection))
        return {"artifacts": {"quest_db": self.original}}

    async def find_one_and_update(self, query, update, **kwargs):
        self.writes.append((query, update, kwargs))
        if self.conflict:
            return None
        return {"polish": {"quest_db": update["$set"]["polish.quest_db"]}}


def model_result(value, *, passed=True, digest=None):
    source, _ = artifact_text(value)
    return {
        "content": source, "score": 97 if passed else 90, "passed": passed,
        "audit_complete": True, "source_sha256": digest or source_digest(source),
        "improved_by": 7, "passes": [], "polished": True,
    }


def setup(monkeypatch, original, result, *, conflict=False):
    from routes import quality_polish_api as api

    collection = Collection(original, conflict=conflict)
    authority = []

    async def access(pid, *, mutate=False):
        authority.append((pid, mutate))

    async def polish(kind, content, *, simulate, max_passes):
        assert kind == "narrative"
        assert content == original
        return result

    monkeypatch.setattr(api, "assert_project_access", access)
    monkeypatch.setattr(api, "polish_pass", polish)
    monkeypatch.setattr(api, "_db", SimpleNamespace(game_kb=collection))
    return api, collection, authority


def test_publish_only_verified_improvement_without_changing_build_holds(monkeypatch):
    original = {"quest": "old", "steps": [1, 2]}
    proposed = {"quest": "new", "steps": [1, 2, 3]}
    api, coll, auth = setup(monkeypatch, original, model_result(proposed))
    result = asyncio.run(api.polish_game_stage("game-1", "narrative", False, 2))
    assert result["persisted"] and result["passed"]
    assert "content" not in result
    assert auth == [("game-1", True), ("game-1", True)]
    assert len(coll.writes) == 1
    query, update, kwargs = coll.writes[0]
    assert query["game_id"] == "game-1"
    assert query["$expr"] == {"$eq": ["$artifacts.quest_db", {"$literal": original}]}
    assert query["revoked"] == {"$ne": True}
    assert kwargs["upsert"] is False
    sets = update["$set"]
    assert set(sets) == {"artifacts.quest_db", "polish.quest_db"}
    assert sets["artifacts.quest_db"] == proposed
    assert sets["polish.quest_db"]["source_sha256"] == result["source_sha256"]
    assert sets["polish.quest_db"]["evidence_scope"] == "model-review-structural-proxy"


@pytest.mark.parametrize("result", [
    model_result({"quest": "new", "steps": [1, 2]}, passed=False),
    model_result({"quest": "new", "steps": [1, 2]}, digest="wrong"),
    model_result({"quest": "new"}),
    model_result({"quest": "old", "steps": [1, 2]}),
])
def test_weak_forged_incompatible_or_unchanged_candidate_does_not_write(monkeypatch, result):
    api, collection, _ = setup(monkeypatch, {"quest": "old", "steps": [1, 2]}, result)
    observation = asyncio.run(api.polish_game_stage("game-1", "narrative", False, 2))
    assert not observation["persisted"]
    assert not collection.writes


def test_concurrent_edit_cannot_be_overwritten(monkeypatch):
    api, collection, _ = setup(
        monkeypatch, {"quest": "old"}, model_result({"quest": "new"}), conflict=True,
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.polish_game_stage("game-1", "narrative", False, 2))
    assert error.value.status_code == 409
    assert len(collection.writes) == 1


def test_denied_owner_cannot_read_or_rewrite(monkeypatch):
    api, coll, _ = setup(monkeypatch, {"quest": "old"}, model_result({"quest": "new"}))

    async def deny(*args, **kwargs):
        raise HTTPException(404, "Game not found")

    monkeypatch.setattr(api, "assert_project_access", deny)
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.polish_game_stage("foreign", "narrative", False, 2))
    assert error.value.status_code == 404
    assert not coll.reads and not coll.writes
