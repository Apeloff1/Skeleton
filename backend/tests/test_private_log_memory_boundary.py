"""ASGI regressions for private log-derived Jeeves memory and exports."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace

from bson import ObjectId
import pytest

from routes import ai_log_vault as route
from backend.tests.test_private_memory_boundary import memory_boundary


def _matches(row, query):
    return all(
        row.get(key) is not None and row[key] >= value["$gte"]
        if isinstance(value, dict) and "$gte" in value else row.get(key) == value
        for key, value in query.items()
    )


class _Cursor:
    def __init__(self, rows):
        self.rows = deepcopy(rows)
    def limit(self, n):
        self.rows = self.rows[:n]
        return self
    def __aiter__(self):
        self.iterator = iter(self.rows)
        return self
    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration:
            raise StopAsyncIteration


class _Collection:
    def __init__(self):
        self.rows = []
        self.queries = []
        self.ignore_filter = False
    async def insert_one(self, row):
        row = deepcopy(row)
        row.setdefault("_id", ObjectId())
        self.rows.append(row)
        return SimpleNamespace(inserted_id=row["_id"])
    def find(self, query):
        self.queries.append(deepcopy(query))
        return _Cursor([row for row in self.rows if self.ignore_filter or _matches(row, query)])
    async def find_one(self, query, sort=None):
        self.queries.append(deepcopy(query))
        rows = [deepcopy(row) for row in self.rows if self.ignore_filter or _matches(row, query)]
        if sort:
            key, direction = sort[0]
            rows.sort(key=lambda row: row.get(key), reverse=direction < 0)
        return rows[0] if rows else None
    async def count_documents(self, query):
        self.queries.append(deepcopy(query))
        return sum(_matches(row, query) for row in self.rows)
    async def update_one(self, query, update):
        self.queries.append(deepcopy(query))
        for row in self.rows:
            if _matches(row, query):
                row.update(deepcopy(update.get("$set", {})))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


@pytest.fixture
def private_log_boundary(memory_boundary, monkeypatch):
    client, headers, users, *_ = memory_boundary
    client.app.include_router(route.router, prefix="/api")
    collections = {}
    for name in ("ai_queries", "user_actions", "training_data", "jeeves_memory", "logscraper_runs"):
        collections[name] = _Collection()
        monkeypatch.setattr(route, name + "_collection", collections[name])
    return client, headers, users, collections


@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/info", None), ("GET", "/stats", None), ("GET", "/export", None),
    ("GET", "/jeeves/memory", None), ("GET", "/scrape/latest", None),
    ("GET", "/scrape/status/some-run", None),
    ("POST", "/query", {"query_type": "chat", "user_input": "private", "ai_response": "private"}),
    ("POST", "/action", {"action_type": "private", "action_data": {}}),
    ("POST", "/feedback/000000000000000000000001?feedback=helpful", None),
    ("POST", "/scrape", {}), ("POST", "/jeeves/train", None),
    ("POST", "/jeeves/remember?memory_type=private", {"canary": "private"}),
    ("POST", "/startup-train", None),
])
def test_log_memory_surfaces_require_authentication(private_log_boundary, method, path, payload):
    client, _, _, collections = private_log_boundary
    assert client.request(method, "/api/ai-logs" + path, json=payload).status_code == 401
    assert all(not collection.rows and not collection.queries for collection in collections.values())


def test_log_memory_export_and_training_are_actor_and_tenant_private(private_log_boundary):
    client, headers, users, collections = private_log_boundary
    own = headers["alice"]
    query = {"query_type": "chat", "user_input": "ALICE-PRIVATE-QUERY-CANARY", "ai_response": "ALICE-PRIVATE-RESPONSE-CANARY", "user_feedback": "helpful"}
    assert client.post("/api/ai-logs/query", headers=own, json=query).status_code == 200
    assert client.post("/api/ai-logs/action", headers=own, json={"action_type": "edit", "action_data": {"private": "alice"}}).status_code == 200
    assert client.post("/api/ai-logs/jeeves/remember?memory_type=private", headers=own, json={"private": "ALICE-PRIVATE-MEMORY-CANARY"}).status_code == 200
    for collection in (collections["ai_queries"], collections["user_actions"], collections["jeeves_memory"]):
        assert collection.rows[0]["owner_id"] == "alice@example.test"
        assert collection.rows[0]["tenant_id"] == "tenant-a"
    assert "ALICE-PRIVATE-MEMORY-CANARY" in client.get("/api/ai-logs/jeeves/memory", headers=own).text
    assert "ALICE-PRIVATE-QUERY-CANARY" in client.get("/api/ai-logs/export", headers=own).text
    assert client.post("/api/ai-logs/scrape", headers=own, json={}).status_code == 200
    trained = client.post("/api/ai-logs/jeeves/train", headers=own)
    assert trained.status_code == 200 and trained.json()["status"] == "training_complete"
    assert "ALICE-PRIVATE-QUERY-CANARY" in client.get("/api/ai-logs/jeeves/memory", headers=own).text
    for actor in ("bob", "alice"):
        if actor == "alice":
            users["alice@example.test"]["tenant_id"] = "tenant-b"
        foreign = headers[actor]
        assert client.get("/api/ai-logs/jeeves/memory", headers=foreign).json()["status"] == "no_memory"
        assert client.get("/api/ai-logs/export", headers=foreign).json()["ai_queries"] == []
        assert client.get("/api/ai-logs/scrape/latest", headers=foreign).json() == {"message": "No scraper runs found"}
        assert client.post("/api/ai-logs/jeeves/train", headers=foreign).json()["status"] == "no_data"
        assert client.get("/api/ai-logs/stats", headers=foreign).json()["jeeves_memories"] == 0
    for collection in collections.values():
        for query in collection.queries:
            assert query.get("owner_id") in {"alice@example.test", "bob@example.test"}
            assert query.get("tenant_id") in {"tenant-a", "tenant-b"}


def test_feedback_cannot_mutate_another_actor_or_tenants_log(private_log_boundary):
    client, headers, users, collections = private_log_boundary
    response = client.post("/api/ai-logs/query", headers=headers["alice"], json={"query_type": "chat", "user_input": "mine", "ai_response": "mine"})
    path = "/api/ai-logs/feedback/" + response.json()["log_id"] + "?feedback=helpful"
    assert client.post(path, headers=headers["bob"]).status_code == 404
    users["alice@example.test"]["tenant_id"] = "tenant-b"
    assert client.post(path, headers=headers["alice"]).status_code == 404
    assert collections["ai_queries"].rows[0]["user_feedback"] is None
    users["alice@example.test"]["tenant_id"] = "tenant-a"
    assert client.post(path, headers=headers["alice"]).status_code == 200


def test_foreign_or_legacy_rows_are_rejected_after_a_faulty_database_filter(private_log_boundary):
    client, headers, _, collections = private_log_boundary
    from datetime import datetime
    for name in ("ai_queries", "training_data", "jeeves_memory", "logscraper_runs"):
        collection = collections[name]
        collection.ignore_filter = True
        collection.rows = [{"_id": ObjectId(), "timestamp": datetime.utcnow(), "completed_at": datetime.utcnow(), "content": "LEGACY-PRIVATE-CANARY", "ready_for_training": True, "data": {"patterns": ["FOREIGN-PRIVATE-CANARY"]}}]
    own = headers["alice"]
    assert client.get("/api/ai-logs/jeeves/memory", headers=own).json()["status"] == "no_memory"
    exported = client.get("/api/ai-logs/export", headers=own)
    assert exported.json()["ai_queries"] == [] and exported.json()["patterns"] == []
    assert client.post("/api/ai-logs/jeeves/train", headers=own).json()["status"] == "no_data"
    assert client.get("/api/ai-logs/scrape/status/legacy", headers=own).json()["status"] == "running"
    assert client.get("/api/ai-logs/scrape/latest", headers=own).json() == {"message": "No scraper runs found"}
    assert client.post("/api/ai-logs/scrape", headers=own, json={}).status_code == 200
    derived = collections["training_data"].rows[-1]
    assert derived["owner_id"] == "alice@example.test" and derived["tenant_id"] == "tenant-a"
    assert derived["data"]["ai_queries"] == []
    assert "PRIVATE-CANARY" not in str(derived)


def test_internal_training_requires_explicit_scope_before_any_database_access(private_log_boundary):
    _, _, _, collections = private_log_boundary
    config = route.LogscraperConfig()
    for operation in (route.execute_logscraper("r", config), route.execute_startup_training("s", config), route.process_jeeves_training({"data": {}})):
        with pytest.raises(ValueError, match="scope"):
            asyncio.run(operation)
    assert all(not collection.rows and not collection.queries for collection in collections.values())
