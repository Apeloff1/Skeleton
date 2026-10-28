"""Exercise private memory admission and ownership through the real ASGI routes."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import agent_memory, canon_rag, gameforge_auth


ALICE = {"email": "alice@example.test", "tenant_id": "tenant-a", "role": "editor"}
SCOPE = {"owner_id": ALICE["email"], "tenant_id": ALICE["tenant_id"]}


def _matches(row, query):
    return all(
        row.get(key) != value["$ne"] if isinstance(value, dict) and "$ne" in value
        else row.get(key) == value
        for key, value in query.items()
    )


class _Cursor:
    def __init__(self, rows):
        self.rows = deepcopy(rows)

    def sort(self, key, direction):
        self.rows.sort(key=lambda row: row.get(key, ""), reverse=direction < 0)
        return self

    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self

    async def to_list(self, limit):
        return deepcopy(self.rows[:limit])


class _Collection:
    """A query-aware Mongo protocol fake with observable authority boundaries."""

    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))
        self.calls = []
        self.ignore_filter = False
        self.fail_writes = False

    def find(self, query, projection=None):
        self.calls.append(("find", deepcopy(query)))
        return _Cursor([row for row in self.rows if self.ignore_filter or _matches(row, query)])

    async def find_one(self, query, projection=None):
        self.calls.append(("find_one", deepcopy(query)))
        return next((deepcopy(row) for row in self.rows
                     if self.ignore_filter or _matches(row, query)), None)

    async def insert_one(self, row):
        self.calls.append(("insert", deepcopy(row)))
        if self.fail_writes:
            raise RuntimeError("private database failure detail")
        self.rows.append(deepcopy(row))

    async def delete_many(self, query):
        self.calls.append(("delete", deepcopy(query)))
        before = len(self.rows)
        self.rows = [row for row in self.rows if not _matches(row, query)]
        return SimpleNamespace(deleted_count=before - len(self.rows))

    def aggregate(self, pipeline):
        self.calls.append(("aggregate", deepcopy(pipeline)))
        rows = self.rows
        if pipeline and "$match" in pipeline[0] and not self.ignore_filter:
            rows = [row for row in rows if _matches(row, pipeline[0]["$match"])]
        grouped = {}
        for row in rows:
            key = row["agent_id"]
            group = grouped.setdefault(key, {
                "_id": key, "tenant_id": row.get("tenant_id"), "owner_id": row.get("owner_id"),
                "memories": 0, "reflections": 0, "last_at": "", "avg_importance": 0.5,
            })
            group["memories"] += 1
            group["reflections"] += int(row.get("kind") == "reflection")
            group["last_at"] = max(group["last_at"], row.get("created_at", ""))
        return _Cursor(list(grouped.values()))


def _memories(scope, marker):
    return [
        {**scope, "agent_id": "shared", "memory_id": marker + str(index),
         "content": marker + " episode " + str(index), "kind": "reflection" if index == 3 else "episode",
         "importance": 0.8, "tags": [marker], "keywords": ["private"],
         "created_at": f"2026-10-23T12:00:0{index}Z"}
        for index in range(4)
    ]


@pytest.fixture
def boundary(monkeypatch):
    memories = _Collection(
        _memories(SCOPE, "ALICE_PRIVATE")
        + _memories({**SCOPE, "owner_id": "bob@example.test"}, "BOB_PRIVATE")
        + _memories({**SCOPE, "tenant_id": "tenant-b"}, "OTHER_TENANT_PRIVATE")
        + _memories({}, "LEGACY_PRIVATE")
    )
    projects = _Collection([
        {**SCOPE, "playable_id": "alice-game", "state": "active"},
        {"playable_id": "legacy-game"},
    ])
    knowledge = _Collection([
        {**SCOPE, "game_id": "alice-game", "artifacts": {
            "core_specs": {"logline": "ALICE_CANON_PRIVATE crystal adventure"}}},
        {"game_id": "legacy-game", "artifacts": {
            "core_specs": {"logline": "LEGACY_CANON_PRIVATE crystal secret"}}},
    ])
    database = SimpleNamespace(agent_memories=memories, playables=projects, game_kb=knowledge)
    monkeypatch.setattr(agent_memory, "_db", database)
    monkeypatch.setattr(canon_rag, "_db", database)
    principal = {"user": deepcopy(ALICE)}
    app = FastAPI()
    app.include_router(agent_memory.router)
    app.include_router(canon_rag.router)
    app.dependency_overrides[gameforge_auth.get_current_user] = lambda: principal["user"]
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, principal=principal, memories=memories,
                              projects=projects, knowledge=knowledge)


PRIVATE_REQUESTS = [
    ("POST", "/api/agent-memory/remember", {"agent_id": "shared", "content": "private"}),
    ("GET", "/api/agent-memory/recall?agent_id=shared", None),
    ("POST", "/api/agent-memory/reflect", {"agent_id": "shared"}),
    ("GET", "/api/agent-memory/agents", None),
    ("GET", "/api/agent-memory/shared/profile", None),
    ("DELETE", "/api/agent-memory/shared", None),
    ("GET", "/api/agent-memory/shared/bias", None),
    ("GET", "/api/rag/alice-game/memory", None),
    ("GET", "/api/rag/alice-game/retrieve?q=crystal", None),
]


@pytest.mark.parametrize("method,path,body", PRIVATE_REQUESTS)
def test_anonymous_private_memory_fails_before_any_storage_access(boundary, method, path, body):
    boundary.principal["user"] = None
    response = boundary.client.request(method, path, json=body)
    assert response.status_code == 401, response.text
    assert boundary.memories.calls == boundary.projects.calls == boundary.knowledge.calls == []
    assert "PRIVATE" not in response.text


@pytest.mark.parametrize("path", [
    "/api/agent-memory/recall?agent_id=shared",
    "/api/agent-memory/shared/profile",
    "/api/agent-memory/shared/bias",
])
def test_agent_reads_return_owner_canary_without_other_scopes(boundary, path):
    response = boundary.client.get(path)
    assert response.status_code == 200, response.text
    assert "ALICE_PRIVATE" in response.text
    assert all(marker not in response.text for marker in ["BOB_PRIVATE", "OTHER_TENANT_PRIVATE", "LEGACY_PRIVATE"])
    assert all(call[1].get(key) == value for call in boundary.memories.calls for key, value in SCOPE.items())


@pytest.mark.parametrize("identity,allowed", [
    ({**ALICE, "email": "bob@example.test"}, "BOB_PRIVATE"),
    ({**ALICE, "tenant_id": "tenant-b"}, "OTHER_TENANT_PRIVATE"),
])
def test_same_agent_name_does_not_cross_actor_or_tenant(boundary, identity, allowed):
    boundary.principal["user"] = identity
    response = boundary.client.get("/api/agent-memory/recall?agent_id=shared")
    assert response.status_code == 200
    assert allowed in response.text
    assert "ALICE_PRIVATE" not in response.text and "LEGACY_PRIVATE" not in response.text


def test_agent_enumeration_is_scoped_before_aggregation(boundary):
    response = boundary.client.get("/api/agent-memory/agents")
    assert response.status_code == 200
    assert response.json()["agents"][0]["memories"] == 4
    assert boundary.memories.calls[0][1][0] == {"$match": SCOPE}


def test_agent_result_validation_discards_foreign_and_legacy_rows(boundary):
    boundary.memories.ignore_filter = True
    response = boundary.client.get("/api/agent-memory/recall?agent_id=shared")
    assert response.status_code == 200
    assert response.json()["count"] == 4
    assert all(marker not in response.text for marker in ["BOB_PRIVATE", "OTHER_TENANT_PRIVATE", "LEGACY_PRIVATE"])


def test_new_agent_memory_uses_principal_and_rejects_scope_spoof(boundary):
    response = boundary.client.post("/api/agent-memory/remember", json={
        "agent_id": "shared", "content": "NEW_ALICE_MEMORY", "owner_id": "bob@example.test"})
    assert response.status_code == 422
    response = boundary.client.post("/api/agent-memory/remember", json={
        "agent_id": "shared", "content": "NEW_ALICE_MEMORY"})
    assert response.status_code == 200, response.text
    assert all(boundary.memories.rows[-1][key] == value for key, value in SCOPE.items())
    boundary.principal["user"] = {**ALICE, "email": "bob@example.test"}
    response = boundary.client.get("/api/agent-memory/recall?agent_id=shared")
    assert "NEW_ALICE_MEMORY" not in response.text


def test_delete_preserves_foreign_tenant_actor_and_unowned_records(boundary):
    before = deepcopy(boundary.memories.rows)
    foreign = [row for row in before if not _matches(row, SCOPE)]
    response = boundary.client.delete("/api/agent-memory/shared")
    assert response.status_code == 200
    assert response.json()["deleted"] == 4
    assert boundary.memories.rows == foreign
    assert boundary.memories.calls[-1] == ("delete", {**SCOPE, "agent_id": "shared"})


def test_reflection_uses_only_owned_episodes_and_verified_provider_scope(boundary, monkeypatch):
    calls = []

    async def complete(task, prompt, **kwargs):
        calls.append((task, prompt, kwargs))
        return {"content": "OWNED_REFLECTION", "model": "canonical-fixture"}

    monkeypatch.setattr(agent_memory, "route_complete", complete)
    # A wrongly mixed backend result still must not enter the model prompt.
    boundary.memories.ignore_filter = True
    response = boundary.client.post("/api/agent-memory/reflect", json={"agent_id": "shared"})
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    _, prompt, kwargs = calls[0]
    assert "ALICE_PRIVATE" in prompt
    assert all(marker not in prompt for marker in ["BOB_PRIVATE", "OTHER_TENANT_PRIVATE", "LEGACY_PRIVATE"])
    assert kwargs["tenant_id"] == SCOPE["tenant_id"] and kwargs["actor_id"] == SCOPE["owner_id"]
    assert all(boundary.memories.rows[-1][key] == value for key, value in SCOPE.items())


def test_memory_storage_failure_never_reports_a_committed_receipt(boundary):
    boundary.memories.fail_writes = True
    response = boundary.client.post("/api/agent-memory/remember", json={
        "agent_id": "shared", "content": "UNCOMMITTED_MEMORY"})
    assert response.status_code == 503
    assert "private database failure detail" not in response.text
    assert all(row["content"] != "UNCOMMITTED_MEMORY" for row in boundary.memories.rows)


def test_reflection_storage_failure_never_reports_a_committed_receipt(boundary, monkeypatch):
    async def complete(*args, **kwargs):
        return {"content": "UNCOMMITTED_REFLECTION", "model": "canonical-fixture"}

    monkeypatch.setattr(agent_memory, "route_complete", complete)
    boundary.memories.fail_writes = True
    response = boundary.client.post("/api/agent-memory/reflect", json={"agent_id": "shared"})
    assert response.status_code == 503
    assert "private database failure detail" not in response.text
    assert all(row["content"] != "UNCOMMITTED_REFLECTION" for row in boundary.memories.rows)


def test_signed_jwt_uses_current_canonical_account_scope(boundary, monkeypatch):
    boundary.client.app.dependency_overrides.pop(gameforge_auth.get_current_user)
    users = {
        ALICE["email"]: deepcopy(ALICE),
        "bob@example.test": {**ALICE, "email": "bob@example.test"},
    }

    class Users:
        def find_one(self, query, projection=None):
            row = users.get(query.get("email"))
            return deepcopy(row) if row is not None and _matches(row, query) else None

    monkeypatch.setattr(gameforge_auth, "_secret", lambda: "agent-canon-test-secret-with-32-bytes")
    monkeypatch.setattr(gameforge_auth, "_users", lambda: Users())
    monkeypatch.setattr(gameforge_auth, "_sessions", lambda: SimpleNamespace(find_one=lambda query: None))
    alice = {"Authorization": "Bearer " + jwt.encode(
        {"sub": ALICE["email"], "role": "editor"}, gameforge_auth._secret(), algorithm="HS256")}
    bob = {"Authorization": "Bearer " + jwt.encode(
        {"sub": "bob@example.test", "role": "editor"}, gameforge_auth._secret(), algorithm="HS256")}
    assert boundary.client.get("/api/agent-memory/recall?agent_id=shared").status_code == 401
    assert boundary.memories.calls == []
    own = boundary.client.get("/api/agent-memory/recall?agent_id=shared", headers=alice)
    assert own.status_code == 200 and "ALICE_PRIVATE" in own.text
    other = boundary.client.get("/api/agent-memory/recall?agent_id=shared", headers=bob)
    assert other.status_code == 200 and "ALICE_PRIVATE" not in other.text
    assert boundary.client.get("/api/rag/alice-game/retrieve?q=crystal", headers=alice).status_code == 200
    assert boundary.client.get("/api/rag/alice-game/retrieve?q=crystal", headers=bob).status_code == 404
    users[ALICE["email"]]["tenant_id"] = "tenant-b"
    moved = boundary.client.get("/api/agent-memory/recall?agent_id=shared", headers=alice)
    assert moved.status_code == 200 and "ALICE_PRIVATE" not in moved.text
    assert boundary.client.get("/api/rag/alice-game/retrieve?q=crystal", headers=alice).status_code == 404
    users[ALICE["email"]]["disabled"] = True
    assert boundary.client.get("/api/agent-memory/recall?agent_id=shared", headers=alice).status_code == 401


def test_project_canon_owner_can_read_exact_authorized_source(boundary):
    response = boundary.client.get("/api/rag/alice-game/retrieve?q=crystal")
    assert response.status_code == 200, response.text
    assert "ALICE_CANON_PRIVATE" in response.text
    response = boundary.client.get("/api/rag/alice-game/memory")
    assert response.status_code == 200 and response.json()["chunks"] == 1
    assert all(call[1].get(key) == value for collection in [boundary.projects, boundary.knowledge]
               for call in collection.calls for key, value in SCOPE.items())


@pytest.mark.parametrize("principal", [
    {**ALICE, "email": "bob@example.test"}, {**ALICE, "tenant_id": "tenant-b"},
])
@pytest.mark.parametrize("suffix", ["memory", "retrieve?q=crystal"])
def test_project_canon_denies_wrong_actor_or_tenant_before_reading_kb(boundary, principal, suffix):
    boundary.principal["user"] = principal
    response = boundary.client.get("/api/rag/alice-game/" + suffix)
    assert response.status_code == 404, response.text
    assert "ALICE_CANON_PRIVATE" not in response.text
    assert boundary.knowledge.calls == []


@pytest.mark.parametrize("state", ["revoked", "deleted", "archived"])
def test_project_source_withdrawal_blocks_canon(boundary, state):
    boundary.projects.rows[0]["state"] = state
    response = boundary.client.get("/api/rag/alice-game/retrieve?q=crystal")
    assert response.status_code == 404
    assert boundary.knowledge.calls == []


def test_unowned_legacy_project_and_unowned_kb_never_grant_access(boundary):
    response = boundary.client.get("/api/rag/legacy-game/retrieve?q=crystal")
    assert response.status_code == 404
    boundary.knowledge.rows[0].pop("owner_id")
    response = boundary.client.get("/api/rag/alice-game/retrieve?q=crystal")
    assert response.status_code == 200 and response.json()["hits"] == []
    assert "CANON_PRIVATE" not in response.text


@pytest.mark.parametrize("which", ["projects", "knowledge"])
def test_project_and_canon_result_identity_is_validated(boundary, which):
    collection = getattr(boundary, which)
    collection.rows[0]["owner_id"] = "bob@example.test"
    collection.ignore_filter = True
    response = boundary.client.get("/api/rag/alice-game/retrieve?q=crystal")
    assert response.status_code in {200, 404}
    assert "ALICE_CANON_PRIVATE" not in response.text


def test_unscoped_internal_recall_cannot_export_private_canon(boundary):
    assert asyncio.run(canon_rag._recall("alice-game", "crystal")) == []
    assert boundary.projects.calls == boundary.knowledge.calls == []
