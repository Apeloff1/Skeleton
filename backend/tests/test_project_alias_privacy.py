"""Real JWT/ASGI isolation across indirect project, job and binary aliases."""
from __future__ import annotations

import base64
from copy import deepcopy
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from routes import asset_genesis, collections, gameforge_auth as auth
from routes import photoreal, playable_access as access, snowball_improve, worldforge


def _value(row, key):
    for part in key.split("."):
        row = row.get(part) if isinstance(row, dict) else None
    return row


def _matches(row, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(row, item) for item in expected):
                return False
        elif key == "$and":
            if not all(_matches(row, item) for item in expected):
                return False
        elif isinstance(expected, dict):
            actual = _value(row, key)
            for operator, value in expected.items():
                if operator == "$in" and actual not in value:
                    return False
                if operator == "$ne" and actual == value:
                    return False
        elif _value(row, key) != expected:
            return False
    return True


def _project(row, projection):
    if not projection:
        return deepcopy(row)
    included = {key for key, value in projection.items() if value and key != "_id"}
    if included:
        return {key: deepcopy(row[key]) for key in included if key in row}
    return {key: deepcopy(value) for key, value in row.items() if projection.get(key) != 0}


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *args):
        return self

    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self

    async def to_list(self, length):
        return deepcopy(self.rows[:length])


class Collection:
    def __init__(self, rows=()):
        self.rows = list(deepcopy(rows))
        self.writes = []

    def find(self, query, projection=None):
        return Cursor([_project(row, projection) for row in self.rows if _matches(row, query)])

    async def find_one(self, query, projection=None):
        return next((_project(row, projection) for row in self.rows if _matches(row, query)), None)

    async def insert_one(self, row):
        self.writes.append(("insert", deepcopy(row)))
        self.rows.append(deepcopy(row))
        return SimpleNamespace(inserted_id="inserted")

    async def update_one(self, query, update, **kwargs):
        return await self.update_many(query, update, **kwargs)

    async def update_many(self, query, update, **kwargs):
        self.writes.append(("update", deepcopy(query), deepcopy(update)))
        matches = [row for row in self.rows if _matches(row, query)]
        for row in matches:
            row.update(deepcopy(update.get("$set", {})))
        return SimpleNamespace(matched_count=len(matches), modified_count=len(matches))

    async def delete_one(self, query):
        self.writes.append(("delete", deepcopy(query)))
        found = next((row for row in self.rows if _matches(row, query)), None)
        if found is not None:
            self.rows.remove(found)
        return SimpleNamespace(deleted_count=int(found is not None))


class Database:
    def __init__(self):
        self.tables = {}

    def __getitem__(self, key):
        return self.tables.setdefault(key, Collection())

    def __getattr__(self, key):
        return self[key]


@pytest.fixture
def private_app(monkeypatch):
    owner = {"email": "owner@example.test", "tenant_id": "tenant-a", "role": "editor"}
    foreign = {"email": "foreign@example.test", "tenant_id": "tenant-a", "role": "editor"}
    viewer = {**owner, "email": "viewer@example.test", "role": "viewer"}
    users = {row["email"]: row for row in [owner, foreign, viewer]}

    class Users:
        def find_one(self, query, projection=None):
            row = users.get(query.get("email"))
            return deepcopy(row) if row and _matches(row, query) else None

    monkeypatch.setattr(auth, "_secret", lambda: "isolated-project-alias-auth-test-key-32")
    monkeypatch.setattr(auth, "_users", lambda: Users())
    monkeypatch.setattr(auth, "_sessions", lambda: SimpleNamespace(find_one=lambda *args: None))
    owner_scope = auth.require_authenticated_identity(owner)
    foreign_scope = auth.require_authenticated_identity(foreign)
    other_tenant = {**owner_scope, "tenant_id": "tenant-b"}
    db = Database()
    db.playables.rows = [
        {**owner_scope, "playable_id": "owned", "title": "Owner private game", "status": "ready"},
        {**foreign_scope, "playable_id": "foreign", "title": "FOREIGN SECRET", "status": "ready"},
        {**other_tenant, "playable_id": "other-tenant", "title": "OTHER TENANT SECRET", "status": "ready"},
    ]
    db.asset_genesis.rows = [
        {**owner_scope, "asset_id": "owned-asset", "game_id": "owned", "b64": base64.b64encode(b"owned bytes").decode()},
        {**foreign_scope, "asset_id": "foreign-asset", "game_id": "foreign", "b64": base64.b64encode(b"FOREIGN BLOB").decode()},
        {**other_tenant, "asset_id": "other-tenant-asset", "game_id": "other-tenant", "b64": "eA=="},
        {**owner_scope, "asset_id": "stale-asset", "game_id": "foreign", "b64": "eA=="},
    ]
    db.collections.rows = [
        {**owner_scope, "collection_id": "owned-collection", "name": "Owner collection", "game_ids": ["owned", "foreign"]},
        {**foreign_scope, "collection_id": "foreign-collection", "name": "FOREIGN COLLECTION", "game_ids": ["foreign"]},
    ]
    db.worldforge_worlds.rows = [
        {**owner_scope, "world_id": "owned-world", "source": "playable", "source_id": "owned", "config": {}},
        {**foreign_scope, "world_id": "foreign-world", "source": "playable", "source_id": "foreign", "config": {}},
    ]
    monkeypatch.setattr(access, "_raw_database", lambda: db)
    for module in [collections, worldforge, asset_genesis, photoreal, snowball_improve]:
        monkeypatch.setattr(module, "_db", access.scoped_database(db))
    monkeypatch.setattr(asset_genesis, "_VAULT", access.scoped_database(Database()))
    monkeypatch.setattr(worldforge, "_vault", access.scoped_database(Database()))
    monkeypatch.setattr(worldforge, "build_world", lambda *args: pytest.fail("Denied source reached world execution"))
    monkeypatch.setattr(asset_genesis, "_GEN_JOBS", {"asset-job": {"status": "done", "persisted": True, "b64": "eA=="}})
    monkeypatch.setattr(asset_genesis, "_GEN_JOB_AUTHORITY", {"asset-job": {"identity": owner_scope, "game_id": "owned"}})
    monkeypatch.setattr(photoreal, "_JOBS", {"photo-job": {"status": "done", "saved": True, "pid": "owned", "image": "PRIVATE IMAGE"}})
    monkeypatch.setattr(photoreal, "_JOB_AUTHORITY", {"photo-job": {"identity": owner_scope, "pid": "owned"}})
    monkeypatch.setattr(snowball_improve, "_AUTO_LOOP", {"loop": {"status": "done", "pid": "owned", "passes": [{"private": True}]}})
    monkeypatch.setattr(snowball_improve, "_AUTO_LOOP_AUTHORITY", {"loop": {"identity": owner_scope, "pid": "owned"}})
    app = FastAPI()
    for module in [collections, worldforge, asset_genesis, photoreal, snowball_improve]:
        app.include_router(module.router)
    headers = {name: {"Authorization": "Bearer " + auth.create_access_token(sub=user["email"], role=user["role"])}
               for name, user in {"owner": owner, "foreign": foreign, "viewer": viewer}.items()}
    with TestClient(app) as client:
        yield client, headers, db, users


@pytest.mark.parametrize("path", [
    "/api/collections", "/api/worldforge/sources", "/api/assets/genesis/list",
    "/api/photoreal/job/photo-job", "/api/snowball/auto-loop/loop",
])
def test_private_aliases_require_actual_authentication(private_app, path):
    client, _, _, _ = private_app
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", [
    "/api/assets/genesis/job/asset-job", "/api/photoreal/job/photo-job", "/api/snowball/auto-loop/loop",
])
def test_process_job_alias_is_owned_and_rechecks_current_source(private_app, path):
    client, headers, db, _ = private_app
    assert client.get(path, headers=headers["foreign"]).status_code == 404
    own = client.get(path, headers=headers["owner"])
    assert own.status_code == 200, own.text
    assert own.headers["cache-control"] == "private, no-store"
    db.playables.rows[0]["state"] = "revoked"
    assert client.get(path, headers=headers["owner"]).status_code == 404


@pytest.mark.parametrize("asset", ["foreign-asset", "other-tenant-asset", "stale-asset"])
def test_blob_and_delete_check_both_owner_and_source(private_app, asset):
    client, headers, db, _ = private_app
    assert client.get("/api/assets/genesis/" + asset + ".png", headers=headers["owner"]).status_code == 404
    assert client.delete("/api/assets/genesis/" + asset, headers=headers["owner"]).status_code == 404
    assert not db.asset_genesis.writes


def test_owned_blob_is_private_and_not_shared_cacheable(private_app):
    client, headers, _, _ = private_app
    response = client.get("/api/assets/genesis/owned-asset.png", headers=headers["owner"])
    assert response.status_code == 200 and response.content == b"owned bytes"
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("assets", [["foreign-asset"], ["owned-asset", "foreign-asset"], ["stale-asset"]])
def test_link_requires_every_source_asset_before_any_target_write(private_app, assets):
    client, headers, db, _ = private_app
    response = client.post("/api/assets/genesis/link", headers=headers["owner"], json={"game_id": "owned", "asset_ids": assets})
    assert response.status_code == 404, response.text
    assert not db.asset_genesis.writes and not db.playables.writes


def test_collection_and_world_lists_do_not_hydrate_foreign_metadata(private_app):
    client, headers, _, _ = private_app
    for path in ["/api/collections", "/api/collections/owned-collection", "/api/worldforge/sources", "/api/worldforge/worlds"]:
        response = client.get(path, headers=headers["owner"])
        assert response.status_code == 200, response.text
        assert "FOREIGN" not in response.text and "OTHER TENANT" not in response.text
    collection = client.get("/api/collections/owned-collection", headers=headers["owner"]).json()
    assert collection["game_ids"] == ["owned"]
    assert client.get("/api/collections/foreign-collection", headers=headers["owner"]).json() == {"error": "not found"}


def test_indirect_world_sources_fail_before_execution(private_app):
    client, headers, _, _ = private_app
    for source, pid, expected in [("playable", "foreign", 404), ("playable", "other-tenant", 404), ("galaxy", "private-build", 404)]:
        response = client.post("/api/worldforge/from-game", headers=headers["owner"], json={"source": source, "source_id": pid})
        assert response.status_code == expected, response.text


def test_current_role_revocation_denies_mutation_even_with_original_editor_jwt(private_app):
    client, headers, db, users = private_app
    users["owner@example.test"]["role"] = "viewer"
    response = client.post("/api/assets/genesis/link", headers=headers["owner"], json={"game_id": "owned", "asset_ids": ["owned-asset"]})
    assert response.status_code == 403
    assert not db.asset_genesis.writes and not db.playables.writes


def _world(cfg):
    return {"name": "Owned world", "scale": cfg.scale, "stats": {
        "water_pct": 30, "river_tiles": 0, "lakes": 0, "land_pct": 70,
    }, "distribution": [{"label": "forest", "pct": 70}], "pois": [], "region": {}}


@pytest.mark.parametrize("alias", ["owned-vault", "owned-build"])
def test_owned_galaxy_vault_alias_can_create_read_and_list_a_private_world(private_app, monkeypatch, alias):
    client, headers, db, _ = private_app
    scope = {"tenant_id": "tenant-a", "owner_id": "owner@example.test"}
    db.galaxy_vault.rows = [{**scope, "vault_id": "owned-vault", "build_id": "owned-build", "title": "Private build"},
                            {"tenant_id": "tenant-a", "owner_id": "foreign@example.test", "vault_id": "foreign-vault", "title": "FOREIGN"}]
    monkeypatch.setattr(worldforge, "build_world", _world)
    created = client.post("/api/worldforge/from-game", headers=headers["owner"], json={"source": "galaxy", "source_id": alias})
    assert created.status_code == 200, created.text
    assert created.json()["saved"] is True
    assert db.worldforge_worlds.rows[-1]["owner_id"] == scope["owner_id"]
    wid = created.json()["world_id"]
    assert client.get("/api/worldforge/worlds/" + wid, headers=headers["owner"]).status_code == 200
    assert client.get("/api/worldforge/worlds/" + wid, headers=headers["foreign"]).status_code == 404
    sources = client.get("/api/worldforge/sources", headers=headers["owner"])
    assert sources.status_code == 200 and "owned-vault" in sources.text and "FOREIGN" not in sources.text
    db.galaxy_vault.rows[0]["rights_revoked"] = True
    assert client.get("/api/worldforge/worlds/" + wid, headers=headers["owner"]).status_code == 404
    listed = client.get("/api/worldforge/worlds", headers=headers["owner"])
    assert listed.status_code == 200 and wid not in listed.text


def test_asset_list_skips_stale_links_without_hiding_usable_owned_assets(private_app):
    client, headers, _, _ = private_app
    response = client.get("/api/assets/genesis/list", headers=headers["owner"])
    assert response.status_code == 200, response.text
    assert [row["asset_id"] for row in response.json()["assets"]] == ["owned-asset"]


@pytest.mark.parametrize("revoke", [False, True])
def test_world_lore_reauthorizes_and_uses_private_model_identity(private_app, monkeypatch, revoke):
    client, headers, _, users = private_app
    calls = []
    monkeypatch.setattr(worldforge, "build_world", _world)
    async def complete(*args, **kwargs):
        calls.append(kwargs)
        if revoke:
            users["owner@example.test"]["role"] = "viewer"
        return {"content": "PRIVATE-LORE-CANARY"}
    monkeypatch.setattr(worldforge, "route_complete", complete)
    response = client.post("/api/worldforge/lore", headers=headers["owner"], json={})
    assert calls[0]["tenant_id"] == "tenant-a" and calls[0]["actor_id"] == "owner@example.test"
    assert calls[0]["data_class"] == "confidential"
    assert response.status_code == (403 if revoke else 200), response.text
    assert ("PRIVATE-LORE-CANARY" in response.text) is not revoke


@pytest.mark.parametrize("module_name", ["asset_genesis", "photoreal"])
@pytest.mark.parametrize("revoke", [False, True])
def test_image_worker_keeps_verified_identity_and_rejects_revoked_result(private_app, monkeypatch, module_name, revoke):
    from core import engine_chat, render_quality
    client, headers, db, _ = private_app
    calls = []
    class Chat:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def with_model(self, *args):
            return self
        def with_params(self, **kwargs):
            return self
        async def send_message_multimodal_response(self, message):
            if revoke:
                db.playables.rows[0]["revoked"] = True
            return "", [{"data": "PRIVATE-IMAGE-CANARY", "mime_type": "image/png"}]
    monkeypatch.setattr(engine_chat, "EngineChat", Chat)
    monkeypatch.setattr(render_quality, "upscale_b64", lambda value: value)
    router = access.project_router(prefix="/test-studio-worker")
    @router.post("/{pid}")
    async def worker(pid: str):
        if module_name == "asset_genesis":
            await asset_genesis._run_generation(asset_genesis._single_worker, "worker", "item", "private", "private", {"game_id": pid})
            return asset_genesis._GEN_JOBS["worker"]
        await photoreal._run_worker("worker", pid, "cover", "private", "private")
        return photoreal._JOBS["worker"]
    client.app.include_router(router)
    response = client.post("/test-studio-worker/owned", headers=headers["owner"])
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    assert calls[0]["tenant_id"] == "tenant-a" and calls[0]["actor_id"] == "owner@example.test"
    assert calls[0]["data_class"] == "confidential"
    assert response.json()["status"] == ("error" if revoke else "done")
    assert ("PRIVATE-IMAGE-CANARY" in response.text) is not revoke


@pytest.mark.parametrize("revoke", [False, True])
def test_upgrade_proposal_rechecks_source_after_private_model_call(private_app, monkeypatch, revoke):
    from routes import llm_router
    client, headers, db, _ = private_app
    calls = []
    async def audit(pid, **kwargs):
        return {"title": "Private game", "at": "now", "gate_floor": 40, "threshold": 95,
                "deliverable": False, "blocker_count": 1, "blockers": [{"level": "Canon", "score": 40}],
                "levels": [{"key": "canon_consistency", "label": "Canon", "score": 40, "band": "low", "pass": False}]}
    async def complete(*args, **kwargs):
        calls.append(kwargs)
        if revoke:
            db.playables.rows[0]["rights_revoked"] = True
        return {"content": '[{"signal":"Canon","current":40,"upgrade":"PRIVATE-UPGRADE-CANARY","impact":"Coherence"}]'}
    monkeypatch.setattr(snowball_improve, "snowball_audit", audit)
    monkeypatch.setattr(snowball_improve, "_compile_gdd", lambda *args: "Private canon")
    monkeypatch.setattr(llm_router, "route_complete", complete)
    response = client.post("/api/snowball/owned/auto-improve", headers=headers["owner"])
    assert response.status_code == (404 if revoke else 200), response.text
    assert calls[0]["tenant_id"] == "tenant-a" and calls[0]["actor_id"] == "owner@example.test"
    assert calls[0]["data_class"] == "confidential"
    assert ("PRIVATE-UPGRADE-CANARY" in response.text) is not revoke
    if revoke:
        assert not db.snowball_improve_runs.writes
    else:
        assert db.snowball_improve_runs.rows[0]["owner_id"] == "owner@example.test"
