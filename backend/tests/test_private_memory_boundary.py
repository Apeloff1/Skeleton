"""Authenticated ASGI privacy checks for the registered product memory adapters."""
from copy import deepcopy

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import gameforge_auth as auth
from routes import jeeves_core, memory_engine
from services.rag_service import MockCollection
from backend.tests.test_rag_state_authority import _service


class _VectorCollection(MockCollection):
    def get(self, ids=None, where=None, include=None):
        return super().get(ids=ids, where=where)


@pytest.fixture
def memory_boundary(monkeypatch):
    users = {
        "alice@example.test": {"email": "alice@example.test", "tenant_id": "tenant-a", "role": "viewer"},
        "bob@example.test": {"email": "bob@example.test", "tenant_id": "tenant-a", "role": "viewer"},
    }

    class Users:
        def find_one(self, query, projection=None):
            return deepcopy(users.get(query.get("email")))

    class Sessions:
        def find_one(self, query):
            return None

    monkeypatch.setattr(auth, "_secret", lambda: "private-memory-test-secret-32-bytes")
    monkeypatch.setattr(auth, "_users", lambda: Users())
    monkeypatch.setattr(auth, "_sessions", lambda: Sessions())
    memory = jeeves_core.JeevesMemoryRAG()
    memory.initialized = True
    memory.collection = _VectorCollection("private-test")
    monkeypatch.setattr(jeeves_core, "jeeves_memory", memory)
    service, state, db, projections = _service()
    monkeypatch.setattr("services.rag_service.RAGService", lambda: service)
    app = FastAPI()
    app.include_router(memory_engine.router)
    app.include_router(jeeves_core.router)
    headers = {
        name: {"Authorization": "Bearer " + jwt.encode({"sub": name + "@example.test", "role": "viewer"}, auth._secret(), algorithm="HS256")}
        for name in ("alice", "bob")
    }
    with TestClient(app) as client:
        yield client, headers, users, memory, service, state, db, projections


@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/api/memory-engine/status", None),
    ("GET", "/api/memory-engine/prefix", None),
    ("GET", "/api/memory-engine/savings", None),
    ("POST", "/api/memory-engine/prefix/warm", {}),
    ("POST", "/api/memory-engine/compose", {"query": "secret"}),
    ("POST", "/api/jeeves-core/memory/store", {"memory_type": "private", "content": "secret"}),
    ("POST", "/api/jeeves-core/memory/retrieve", {"query": "secret"}),
    ("GET", "/api/jeeves-core/memory/stats", None),
    ("POST", "/api/jeeves-core/co-coding/session", {"pipeline": "python", "initial_prompt": "secret"}),
])
def test_private_memory_endpoints_require_authentication(memory_boundary, method, path, payload):
    client, _, _, memory, *_ = memory_boundary
    response = client.request(method, path, json=payload)
    assert response.status_code == 401
    assert memory.collection.count() == 0


@pytest.mark.parametrize("field,value", [("owner_id", "bob@example.test"), ("tenant_id", "tenant-b"), ("user_id", "bob@example.test")])
def test_memory_metadata_cannot_claim_another_principal(memory_boundary, field, value):
    client, headers, _, memory, *_ = memory_boundary
    response = client.post("/api/jeeves-core/memory/store", headers=headers["alice"], json={
        "memory_type": "private", "content": "canary", "metadata": {field: value},
    })
    assert response.status_code == 403
    assert memory.collection.count() == 0


@pytest.mark.parametrize("path,payload", [
    ("/api/memory-engine/compose", {"query": "secret", "user_id": "bob@example.test"}),
    ("/api/jeeves-core/co-coding/session", {"user_id": "bob@example.test", "pipeline": "python", "initial_prompt": "secret"}),
])
def test_body_user_id_is_only_an_assertion(memory_boundary, path, payload):
    client, headers, *_ = memory_boundary
    assert client.post(path, headers=headers["alice"], json=payload).status_code == 403


def test_private_vector_canary_is_isolated_by_actor_and_tenant(memory_boundary, monkeypatch):
    client, headers, users, memory, *_ = memory_boundary
    response = client.post("/api/jeeves-core/memory/store", headers=headers["alice"], json={
        "memory_type": "private", "content": "ALICE-TENANT-A-PRIVATE-CANARY",
    })
    assert response.status_code == 200 and response.json()["stored"] is True
    memory.collection.add(["LEGACY-UNOWNED-CANARY"], [{"type": "private"}], ["legacy"])
    queries = []
    original_query = memory.collection.query
    def query(**kwargs):
        queries.append(kwargs["where"])
        return original_query(**kwargs)
    monkeypatch.setattr(memory.collection, "query", query)
    own = client.post("/api/jeeves-core/memory/retrieve", headers=headers["alice"], json={"query": "canary"})
    assert [row["content"] for row in own.json()["results"]] == ["ALICE-TENANT-A-PRIVATE-CANARY"]
    assert queries == [{"$and": [{"owner_id": "alice@example.test"}, {"tenant_id": "tenant-a"}]}]
    for actor in ("bob", "alice"):
        if actor == "alice":
            users["alice@example.test"]["tenant_id"] = "tenant-b"
        result = client.post("/api/jeeves-core/memory/retrieve", headers=headers[actor], json={"query": "canary"})
        assert result.status_code == 200 and result.json()["results"] == []
        assert client.get("/api/jeeves-core/memory/stats", headers=headers[actor]).json()["total_memories"] == 0


def test_compose_validates_mongo_authority_and_tenant(memory_boundary, monkeypatch):
    client, headers, users, _, service, state, db, projections = memory_boundary
    service.store_cocoding_context("private-session", "alice@example.test", "python", "MONGO-PRIVATE-CANARY", [], [], tenant_id="tenant-a")
    db[state.COCODING].rows.append({"session_id": "legacy", "user_id": "alice@example.test", "context": "LEGACY-PRIVATE-CANARY"})
    projection = projections.collections["jeeves_cocoding_context"]
    queries = []
    def untrusted_projection(**kwargs):
        queries.append(kwargs["where"])
        return {"ids": [["private-session", "legacy"]], "distances": [[0, 0]], "documents": [["FORGED-VECTOR-CANARY", "LEGACY"]]}
    monkeypatch.setattr(projection, "query", untrusted_projection)
    result = client.post("/api/memory-engine/compose", headers=headers["alice"], json={"query": "canary"})
    assert result.status_code == 200
    assert "MONGO-PRIVATE-CANARY" in result.json()["prompt"]
    assert "FORGED-VECTOR-CANARY" not in result.text and "LEGACY-PRIVATE-CANARY" not in result.text
    assert queries[0] == {"$and": [{"user_id": "alice@example.test"}, {"tenant_id": "tenant-a"}]}
    for actor in ("bob", "alice"):
        if actor == "alice":
            users["alice@example.test"]["tenant_id"] = "tenant-b"
        result = client.post("/api/memory-engine/compose", headers=headers[actor], json={"query": "canary"})
        assert result.status_code == 200 and result.json()["retrieved_count"] == 0
        assert "MONGO-PRIVATE-CANARY" not in result.text


def test_jeeves_discards_cross_scope_results_even_if_vector_filter_is_ignored(memory_boundary, monkeypatch):
    client, headers, _, memory, *_ = memory_boundary
    monkeypatch.setattr(memory.collection, "query", lambda **kwargs: {
        "documents": [["OTHER-ACTOR-CANARY", "OTHER-TENANT-CANARY", "UNOWNED-CANARY"]],
        "metadatas": [[{"owner_id": "bob@example.test", "tenant_id": "tenant-a"}, {"owner_id": "alice@example.test", "tenant_id": "tenant-b"}, {}]],
        "distances": [[0, 0, 0]],
    })
    result = client.post("/api/jeeves-core/memory/retrieve", headers=headers["alice"], json={"query": "canary"})
    assert result.status_code == 200 and result.json()["results"] == []


def test_direct_unscoped_retrieval_cannot_include_new_private_rows(memory_boundary):
    import asyncio
    _, _, _, memory, service, *_ = memory_boundary
    scope = {"owner_id": "alice@example.test", "tenant_id": "tenant-a"}
    asyncio.run(memory.store_memory("private", "private", scope=scope))
    assert asyncio.run(memory.retrieve_memories("private"))["results"] == []
    assert asyncio.run(memory.get_memory_stats())["total_memories"] == 0
    with pytest.raises(ValueError, match="scope"):
        asyncio.run(memory.store_memory("private", "unowned"))
    service.store_cocoding_context("s", scope["owner_id"], "python", "private", [], [], tenant_id=scope["tenant_id"])
    assert service.get_relevant_context(scope["owner_id"], "private") == []


def test_cocoding_session_uses_authenticated_scope(memory_boundary):
    client, headers, _, memory, *_ = memory_boundary
    result = client.post("/api/jeeves-core/co-coding/session", headers=headers["alice"], json={"pipeline": "python", "initial_prompt": "mine"})
    assert result.status_code == 200
    assert result.json()["session"]["user_id"] == "alice@example.test"
    assert result.json()["session"]["tenant_id"] == "tenant-a"
    assert memory.collection._documents[0]["metadata"]["owner_id"] == "alice@example.test"


@pytest.mark.parametrize("path,payload", [
    ("/api/memory-engine/compose", {"query": "private", "tenant_id": "tenant-b"}),
    ("/api/jeeves-core/memory/retrieve", {"query": "private", "owner_id": "bob@example.test"}),
    ("/api/jeeves-core/memory/store", {"content": "private", "memory_type": "private", "tenant_id": "tenant-b"}),
    ("/api/jeeves-core/co-coding/session", {"pipeline": "python", "initial_prompt": "private", "tenant_id": "tenant-b"}),
])
def test_private_requests_reject_extra_identity_fields(memory_boundary, path, payload):
    client, headers, *_ = memory_boundary
    assert client.post(path, headers=headers["alice"], json=payload).status_code == 422


@pytest.mark.parametrize("principal,status", [
    (None, 401),
    ({"email": "anonymous", "role": "admin"}, 401),
    ({"email": "alice@example.test", "tenant_id": "tenant-a", "dev_mode": True}, 401),
    ({"email": "alice@example.test", "tenant_id": " "}, 403),
    ({"email": "alice@example.test", "tenant_id": {"$ne": None}}, 403),
])
def test_private_scope_dependency_has_no_development_or_malformed_identity_bypass(principal, status):
    app = FastAPI()
    app.include_router(memory_engine.router)
    app.dependency_overrides[auth.get_current_user] = lambda: principal
    with TestClient(app) as client:
        assert client.post("/api/memory-engine/compose", json={"query": "private"}).status_code == status


def test_legacy_vector_projection_cannot_import_private_ownership(memory_boundary):
    _, _, _, _, service, state, db, projections = memory_boundary
    projections.collections["jeeves_cocoding_context"].add(
        ["UNTRUSTED-LEGACY-CONTENT"],
        [{"user_id": "alice@example.test", "tenant_id": "tenant-a", "pipeline": "python"}],
        ["legacy-claim"],
    )
    result = service.migrate_legacy_chroma_state()
    assert result["cocoding_context"] == 0
    assert result["skipped"] == 1
    assert db[state.COCODING].rows == []
