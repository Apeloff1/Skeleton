"""Real JWT + ASGI creation remains usable under the private project boundary."""
from copy import deepcopy
from types import SimpleNamespace
import asyncio
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from backend.tests.test_private_memory_boundary import memory_boundary
from routes import playable, playable_access, creator_prefs
from core import databases, engine_chat


def _matches(row, query):
    for key, value in query.items():
        if isinstance(value, dict) and "$in" in value:
            if row.get(key) not in value["$in"]:
                return False
        elif isinstance(value, dict) and "$nin" in value:
            if row.get(key) in value["$nin"]:
                return False
        elif isinstance(value, dict) and "$ne" in value:
            if row.get(key) == value["$ne"]:
                return False
        elif row.get(key) != value:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = deepcopy(rows)
    def sort(self, key, direction):
        self.rows.sort(key=lambda row: row.get(key, ""), reverse=direction < 0)
        return self
    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self
    async def to_list(self, length=None):
        return deepcopy(self.rows[:length])


class _Collection:
    def __init__(self):
        self.rows, self.calls = [], []
        self.writes = []
    async def insert_one(self, row):
        self.calls.append(("insert", deepcopy(row)))
        self.rows.append(deepcopy(row))
        return SimpleNamespace(inserted_id="new")
    def find(self, query, projection=None, *args, **kwargs):
        self.calls.append(("find", deepcopy(query)))
        return _Cursor([row for row in self.rows if _matches(row, query)])
    async def find_one(self, query, projection=None, *args, **kwargs):
        self.calls.append(("find_one", deepcopy(query)))
        return next((deepcopy(row) for row in self.rows if _matches(row, query)), None)
    async def update_one(self, query, update, *args, **kwargs):
        self.calls.append(("update", deepcopy(query)))
        self.writes.append((deepcopy(query), deepcopy(update)))
        for row in self.rows:
            if _matches(row, query):
                row.update(deepcopy(update.get("$set", {})))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


class _Database:
    def __init__(self):
        self.collections = {}
    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())
    def __getattr__(self, name):
        return self[name]


@pytest.fixture
def project_boundary(memory_boundary, monkeypatch):
    client, headers, users, *_ = memory_boundary
    users["alice@example.test"]["role"] = "editor"
    users["bob@example.test"]["role"] = "editor"
    database = _Database()
    monkeypatch.setattr(playable_access, "_raw_database", lambda: database)
    monkeypatch.setattr(playable, "_db", playable_access.scoped_database(database))
    async def bias(creator_id):
        return ""
    monkeypatch.setattr(creator_prefs, "preference_bias", bias)
    async def codegen(*args):
        return {
            "routed": {"model": "hermetic", "provider": "test"},
            "html": "<!DOCTYPE html><html>PRIVATE-NEW-PLAYABLE-CANARY</html>",
            "removed": [], "val": {"score": 100, "missing": [], "structurally_complete": True},
            "trail": [], "evaluation": {"available": False},
        }
    monkeypatch.setattr(playable, "_codegen_quality_loop", codegen)
    client.app.include_router(playable.router)
    return client, headers, users, database


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/generate", {"brief": "A private offline game"}),
    ("POST", "/generate/async", {"brief": "A private offline game"}),
    ("POST", "/import-build/async", {"build_id": "foreign"}),
    ("GET", "/list", None), ("GET", "/some-game/raw", None),
    ("GET", "/some-game/lineage", None), ("GET", "/job/some-job", None),
])
def test_playable_private_surface_rejects_anonymous_before_storage(project_boundary, method, path, body):
    client, _, _, database = project_boundary
    response = client.request(method, "/api/playable" + path, json=body)
    assert response.status_code == 401
    assert not database.collections


def test_fresh_private_creation_is_usable_and_isolated(project_boundary):
    client, headers, users, database = project_boundary
    created = client.post("/api/playable/generate", headers=headers["alice"], json={"brief": "A private offline game", "depth": "fast"})
    assert created.status_code == 200, created.text
    document = created.json()
    assert document["owner_id"] == "alice@example.test"
    assert document["tenant_id"] == "tenant-a"
    assert document["status"] == "ready"
    pid = document["playable_id"]
    assert database.playables.rows[0]["owner_id"] == "alice@example.test"
    assert "PRIVATE-NEW-PLAYABLE-CANARY" in client.get(f"/api/playable/{pid}/raw", headers=headers["alice"]).text
    for actor in ("bob", "alice"):
        if actor == "alice":
            users["alice@example.test"]["tenant_id"] = "tenant-b"
        foreign = headers[actor]
        assert client.get("/api/playable/list", headers=foreign).json()["playables"] == []
        raw = client.get(f"/api/playable/{pid}/raw", headers=foreign)
        assert raw.status_code == 404 and "PRIVATE-NEW-PLAYABLE-CANARY" not in raw.text


def test_raw_game_response_is_sandboxed_even_on_direct_navigation(project_boundary):
    client, headers, _, database = project_boundary
    database.playables.rows.append({
        "playable_id": "raw-csp-game", "owner_id": "alice@example.test", "tenant_id": "tenant-a",
        "html": "<!doctype html><html><head></head><body><script>window.gameBooted=true</script></body></html>",
    })
    path = "/api/playable/raw-csp-game/raw"
    response = client.get(path, headers=headers["alice"])
    assert response.status_code == 200
    policy = response.headers["content-security-policy"]
    assert "sandbox allow-scripts allow-pointer-lock" in policy
    assert "allow-same-origin" not in policy and "allow-top-navigation" not in policy
    for directive in ("default-src 'none'", "connect-src 'none'", "frame-src 'none'", "form-action 'none'", "frame-ancestors 'none'"):
        assert directive in policy
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "window.gameBooted=true" in response.text
    assert client.get(path, headers=headers["bob"]).status_code == 404
    assert client.get(path).status_code == 401


def test_direct_raw_response_is_opaque_and_offline_in_real_chromium(project_boundary):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node and a local Playwright/Chromium installation are required")
    client, headers, _, database = project_boundary
    html = """<!doctype html><html><head></head><body><script>
    (async function () {
      const result = {scriptRan:true, cookieDenied:false, storageDenied:false, fetchDenied:false};
      try { void document.cookie; } catch (_) { result.cookieDenied=true; }
      try { localStorage.getItem('private_app_canary'); } catch (_) { result.storageDenied=true; }
      try { await fetch('/exfil'); } catch (_) { result.fetchDenied=true; }
      document.body.dataset.result=JSON.stringify(result); document.body.dataset.done='yes';
    })();</script></body></html>"""
    database.playables.rows.append({
        "playable_id": "browser-csp-game", "owner_id": "alice@example.test", "tenant_id": "tenant-a", "html": html,
    })
    response = client.get("/api/playable/browser-csp-game/raw", headers=headers["alice"])
    assert response.status_code == 200
    body = json.dumps({"headers": {key: response.headers[key] for key in (
        "content-type", "content-security-policy", "cache-control", "x-content-type-options", "referrer-policy",
    )}, "html": response.text})
    canary = Path(__file__).with_name("playable_raw_browser_canary.cjs")
    result = subprocess.run([node, str(canary)], input=body, capture_output=True, text=True, timeout=40)
    if result.returncode == 77:
        pytest.skip("Playwright with a Chromium executable is unavailable")
    assert result.returncode == 0, result.stderr
    assert "opaque, network-isolated sandbox" in result.stdout


@pytest.mark.parametrize("path,payload,status", [
    ("/generate", {"brief": "Private game brief", "creator_id": "bob@example.test"}, 403),
    ("/generate/async", {"brief": "Private game brief", "creator_id": "bob@example.test"}, 403),
    ("/generate", {"brief": "Private game brief", "spec_id": "foreign-spec"}, 404),
    ("/import-build/async", {"build_id": "foreign-build"}, 404),
])
def test_wrong_creator_or_source_cannot_create_private_artifact(project_boundary, path, payload, status):
    client, headers, _, database = project_boundary
    other = {"tenant_id": "tenant-a", "owner_id": "bob@example.test"}
    database.design_specs.rows.append({**other, "spec_id": "foreign-spec", "gdd": {"logline": "FOREIGN-SPEC-CANARY"}})
    database.galaxy_builds.rows.append({**other, "build_id": "foreign-build", "description": "FOREIGN-BUILD-CANARY"})
    response = client.post("/api/playable" + path, headers=headers["alice"], json=payload)
    assert response.status_code == status, response.text
    assert "FOREIGN-" not in response.text
    assert database.playables.rows == [] and database.playable_jobs.rows == []


def test_viewer_cannot_create_or_enqueue_projects(project_boundary):
    client, headers, users, database = project_boundary
    users["alice@example.test"]["role"] = "viewer"
    for path in ("/generate", "/generate/async"):
        response = client.post("/api/playable" + path, headers=headers["alice"], json={"brief": "A private offline game"})
        assert response.status_code == 403
    assert not database.collections


def test_revocation_during_real_asgi_generation_prevents_late_persistence(project_boundary, monkeypatch):
    client, headers, users, database = project_boundary
    original = playable._codegen_quality_loop
    async def revoke_during_model(*args):
        users["alice@example.test"]["role"] = "viewer"
        return await original(*args)
    monkeypatch.setattr(playable, "_codegen_quality_loop", revoke_during_model)
    response = client.post("/api/playable/generate", headers=headers["alice"], json={"brief": "A private offline game"})
    assert response.status_code == 403
    assert "PRIVATE-NEW-PLAYABLE-CANARY" not in response.text
    assert database.playables.rows == []


def test_spec_revocation_during_model_prevents_late_persistence(project_boundary, monkeypatch):
    client, headers, _, database = project_boundary
    database.design_specs.rows.append({
        "spec_id": "owned-spec", "owner_id": "alice@example.test", "tenant_id": "tenant-a",
        "gdd": {"title": "Private game", "logline": "PRIVATE-SPEC-CANARY"},
    })
    original = playable._codegen_quality_loop
    async def revoke_source(*args):
        database.design_specs.rows[0]["state"] = "revoked"
        return await original(*args)
    monkeypatch.setattr(playable, "_codegen_quality_loop", revoke_source)
    response = client.post("/api/playable/generate", headers=headers["alice"], json={"spec_id": "owned-spec"})
    assert response.status_code == 404, response.text
    assert "PRIVATE-SPEC-CANARY" not in response.text
    assert database.playables.rows == []


@pytest.mark.parametrize("revoke", [False, True])
def test_worker_rechecks_captured_source_with_sync_authority_before_engine_call(project_boundary, monkeypatch, revoke):
    client, headers, _, database = project_boundary
    database.design_specs.rows.append({
        "spec_id": "worker-spec", "owner_id": "alice@example.test", "tenant_id": "tenant-a",
        "gdd": {"title": "private"},
    })
    sync_queries, engine_calls = [], []
    class SyncCollection:
        def __init__(self, name):
            self.name = name
        def find_one(self, query):
            sync_queries.append((self.name, deepcopy(query)))
            return next((deepcopy(row) for row in database[self.name].rows if _matches(row, query)), None)
    class SyncDatabase:
        def __getitem__(self, name):
            return SyncCollection(name)
        def __getattr__(self, name):
            return self[name]
    selected_databases = []
    monkeypatch.delenv("DB_NAME", raising=False)
    def sync_database(name):
        selected_databases.append(name)
        return SyncDatabase()
    monkeypatch.setattr(databases, "get_sync_db", sync_database)
    class Chat:
        def __init__(self, **kwargs):
            engine_calls.append(kwargs)
        def with_model(self, *args):
            return self
        def with_max_tokens(self, value):
            return self
        async def send_message(self, message):
            return "owned model result"
    monkeypatch.setattr(engine_chat, "EngineChat", Chat)
    router = playable_access.project_router(prefix="/test-private-worker")
    @router.post("/source")
    async def source():
        await playable_access.bind_project_source("design_specs", "spec_id", "worker-spec")
        if revoke:
            database.design_specs.rows[0]["state"] = "revoked"
        return await asyncio.to_thread(playable._llm_in_thread, "private", "Bounded instruction", ["test"])
    client.app.include_router(router)
    response = client.post("/test-private-worker/source", headers=headers["alice"])
    assert sync_queries == [("design_specs", {"spec_id": "worker-spec", "tenant_id": "tenant-a", "owner_id": "alice@example.test"})] * (1 if revoke else 2)
    assert selected_databases == ["test_database"] * (1 if revoke else 2)
    if revoke:
        assert response.status_code == 404 and engine_calls == []
    else:
        assert response.status_code == 200 and response.json()["content"] == "owned model result"
        assert engine_calls[0]["tenant_id"] == "tenant-a"
        assert engine_calls[0]["actor_id"] == "alice@example.test"
