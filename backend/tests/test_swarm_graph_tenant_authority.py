"""Tenant-account isolation for graph swarm receipts, history and recall."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core import databases
from routes import agent_swarm as swarm


ALICE = {"tenant_id": "tenant-1", "owner_id": "alice@example.test"}
BOB = {"tenant_id": "tenant-1", "owner_id": "bob@example.test"}
OTHER_TENANT = {"tenant_id": "tenant-2", "owner_id": "alice@example.test"}


@pytest.mark.parametrize("identity", [
    None, {}, {"dev_mode": True}, {"tenant_id": "a"},
    {"tenant_id": "", "owner_id": "user"},
    {"tenant_id": "a", "owner_id": ""},
    {"tenant_id": " a", "owner_id": "user"},
    {"tenant_id": "a", "owner_id": "u\ns"},
    {"tenant_id": "a", "owner_id": " " * 10},
])
def test_invalid_scope_fails_before_graph_io(identity):
    with pytest.raises(HTTPException):
        swarm._owner_scope(identity)


def test_storage_namespace_distinguishes_tenants_and_accounts():
    assert swarm._owner_scope(ALICE)[1] != swarm._owner_scope(BOB)[1]
    assert swarm._owner_scope(ALICE)[1] != swarm._owner_scope(OTHER_TENANT)[1]


def test_public_graph_route_requires_authenticated_principal():
    app = FastAPI()
    app.include_router(swarm.router)
    with TestClient(app) as client:
        assert client.get("/api/swarm-dag/graph/alpha").status_code == 401
        assert client.post("/api/swarm-dag/run", json={
            "directive": "Build original game",
            "project": "alpha",
        }).status_code == 401


def test_graph_history_query_is_bound_to_the_authenticated_owner(monkeypatch):
    observed = []

    class Cursor:
        def sort(self, *_args):
            return self
        async def to_list(self, limit):
            assert limit == 3
            return [{"focus": "owner-only", "tenant_id": "tenant-1", "owner_id": "alice@example.test"}]

    class Collection:
        def find(self, query, projection):
            observed.append(query)
            return Cursor()

    monkeypatch.setattr(databases, "core_db", {"swarm_graph": Collection()})
    result = asyncio.run(swarm.swarm_graph("shared-project", limit=3, identity=ALICE))
    assert result["ok"]
    assert observed == [{"project": "shared-project", **ALICE}]
    # No global project-only query is permitted.
    assert all("tenant_id" in query and "owner_id" in query for query in observed)


def test_private_recall_and_write_share_the_exact_same_principal(monkeypatch):
    reads, writes = [], []

    class Cursor:
        def sort(self, *_args):
            return self
        async def to_list(self, limit):
            assert limit == 3
            return [{"focus": "owned historical context"}]

    class Collection:
        def find(self, query, projection):
            reads.append((query, projection))
            return Cursor()
        async def update_one(self, query, update, *, upsert):
            writes.append((query, update, upsert))
            return SimpleNamespace(acknowledged=True)

    monkeypatch.setattr(databases, "core_db", {"swarm_graph": Collection()})
    result = asyncio.run(swarm._worker(0, "graph", "shared-project", "run-1", ALICE))
    assert result["persisted"] is True
    assert result["recalled"] == ["owned historical context"]
    assert result["memory_mode"] == "owner_scoped_graph"
    assert reads[0][0] == {"project": "shared-project", "type": "Finding", **ALICE}
    assert writes[0][0]["tenant_id"] == ALICE["tenant_id"]
    assert writes[0][0]["owner_id"] == ALICE["owner_id"]
    assert writes[0][1]["$set"]["owner_id"] == ALICE["owner_id"]
    assert writes[0][0]["_id"].startswith(swarm._owner_scope(ALICE)[1])


def test_legacy_unowned_history_is_not_returned_for_any_user(monkeypatch):
    recorded = []

    class Cursor:
        def sort(self, *_args):
            return self
        async def to_list(self, _limit):
            return []

    class Collection:
        def find(self, query, projection):
            recorded.append(query)
            return Cursor()

    monkeypatch.setattr(databases, "core_db", {"swarm_graph": Collection()})
    assert asyncio.run(swarm.swarm_graph("legacy-project", identity=BOB))["nodes"] == []
    assert recorded[0] == {"project": "legacy-project", **BOB}


def test_owner_scope_cannot_reuse_another_users_receipt(monkeypatch):
    async def wrong_owner_worker(index, focus, project, run_id, identity):
        return {
            "worker": index,
            "focus": focus,
            "run_id": run_id,
            "node_id": f"{swarm._owner_scope(BOB)[1]}:{project}:{run_id}:worker:{index}",
            "persisted": True,
        }

    monkeypatch.setattr(swarm, "_worker", wrong_owner_worker)
    result = asyncio.run(swarm.run_swarm(swarm.SwarmReq(
        directive="Build game runtime", workers=2,
    ), identity=ALICE))
    assert result["ok"] is False
    assert result["failed_workers"] == [0, 1]
    assert result["merge"] is None



def test_active_run_capacity_fails_before_graph_access(monkeypatch):
    class Saturated:
        def __init__(self):
            self.releases = 0
        def acquire(self, *, blocking):
            assert blocking is False
            return False
        def release(self):
            self.releases += 1
            raise AssertionError("non-admitted run must not release a slot")

    limiter = Saturated()
    monkeypatch.setattr(swarm, "_RUN_ADMISSION", limiter)
    with pytest.raises(HTTPException) as error:
        asyncio.run(swarm.run_swarm(
            swarm.SwarmReq(directive="Build an original game", workers=32),
            identity=ALICE,
        ))
    assert error.value.status_code == 503
    assert limiter.releases == 0


def test_success_and_failure_always_release_run_capacity(monkeypatch):
    class Limiter:
        active = 0
        def acquire(self, *, blocking):
            assert blocking is False
            self.active += 1
            return True
        def release(self):
            self.active -= 1

    limiter = Limiter()
    monkeypatch.setattr(swarm, "_RUN_ADMISSION", limiter)

    async def failing(_req, _scope, _owner_key):
        raise RuntimeError("worker failed")
    monkeypatch.setattr(swarm, "_run_swarm_scoped", failing)

    with pytest.raises(RuntimeError):
        asyncio.run(swarm.run_swarm(
            swarm.SwarmReq(directive="Build game runtime"),
            identity=ALICE,
        ))
    assert limiter.active == 0


@pytest.mark.parametrize("project", ["", " ", "\x00", " game", "game\nnext", "x" * 201])
def test_project_names_must_be_bounded_printable_text(project):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        swarm.SwarmReq(directive="Build an original game", project=project)


def test_large_directive_does_not_amplify_single_focus_across_32_workers():
    directive = "a" * 10000
    foci = swarm._subtasks(directive, 32)
    assert len(foci) == 32
    assert max(map(len, foci)) <= 128


def test_project_route_rejects_malformed_direct_model_without_dispatch(monkeypatch):
    async def forbidden(_req, _scope, _owner_key):
        raise AssertionError("invalid project reached worker")
    monkeypatch.setattr(swarm, "_run_swarm_scoped", forbidden)
    body = swarm.SwarmReq.model_construct(directive="Build a game", project="bad\nproject", workers=1)
    with pytest.raises(HTTPException) as error:
        asyncio.run(swarm.run_swarm(body, identity=ALICE))
    assert error.value.status_code == 422
