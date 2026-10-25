"""Authenticated project creation, KB and canon retain one usable authority."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_project_alias_privacy import Collection, Cursor, _matches, private_app
from routes import canon_graph, canon_rag, creator_prefs, game_kb, playable, playable_access
from routes import image_generation, playable_cover, snowball_wins
from core import engine_chat
from core import build_journey as journey_core
from routes import build_journey


class WritableCollection(Collection):
    async def update_one(self, query, update, **kwargs):
        self.writes.append(("update", deepcopy(query), deepcopy(update)))
        row = next((row for row in self.rows if _matches(row, query)), None)
        if row is None and kwargs.get("upsert"):
            row = {**deepcopy(query), **deepcopy(update.get("$setOnInsert", {}))}
            self.rows.append(row)
        if row is None:
            return SimpleNamespace(matched_count=0)
        for path, value in update.get("$set", {}).items():
            target = row
            parts = path.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = deepcopy(value)
        return SimpleNamespace(matched_count=1)


@pytest.fixture
def pipeline_app(private_app, monkeypatch):
    client, headers, db, users = private_app
    db.tables["game_kb"] = WritableCollection()
    for module in [playable, game_kb, canon_graph, creator_prefs, playable_cover, snowball_wins, journey_core]:
        monkeypatch.setattr(module, "_db", playable_access.scoped_database(db))
    monkeypatch.setattr(canon_rag, "_db", db)
    async def bias(*args):
        return ""
    async def codegen(*args):
        return {"routed": {"provider": "test", "model": "hermetic"},
                "html": "<html>OWNER PRIVATE GAME</html>", "removed": [],
                "val": {"score": 100, "missing": []}, "trail": []}
    monkeypatch.setattr(creator_prefs, "preference_bias", bias)
    monkeypatch.setattr(playable, "_codegen_quality_loop", codegen)
    for module in [playable, game_kb, canon_graph, canon_rag, playable_cover, snowball_wins, creator_prefs, build_journey]:
        client.app.include_router(module.router)
    return client, headers, db, users


def test_fresh_game_to_private_kb_to_canon_is_usable_and_isolated(pipeline_app):
    client, headers, db, users = pipeline_app
    created = client.post("/api/playable/generate", headers=headers["owner"], json={"brief": "Private forest game", "depth": "fast"})
    assert created.status_code == 200, created.text
    pid = created.json()["playable_id"]
    artifacts = {"core_specs": {"logline": "OWNER FOREST CANARY", "pillars": ["Explore"]},
                 "lore_graph": {"regions": [{"name": "Hidden Forest", "description": "OWNER FOREST CANARY"}]}}
    for artifact, data in artifacts.items():
        saved = client.put(f"/api/pipeline/{pid}/kb/{artifact}", headers=headers["owner"], json={"data": data})
        assert saved.status_code == 200 and saved.json()["ok"], saved.text
    row = db.game_kb.rows[0]
    assert row["owner_id"] == "owner@example.test" and row["tenant_id"] == "tenant-a"
    graph = client.get(f"/api/graph/{pid}", headers=headers["owner"])
    recall = client.get(f"/api/rag/{pid}/retrieve?q=forest", headers=headers["owner"])
    assert graph.status_code == recall.status_code == 200
    assert "Hidden Forest" in graph.text and "OWNER FOREST CANARY" in recall.text
    for path in [f"/api/graph/{pid}", f"/api/rag/{pid}/retrieve?q=forest", f"/api/playable/{pid}/raw"]:
        denied = client.get(path, headers=headers["foreign"])
        assert denied.status_code == 404 and "OWNER" not in denied.text
    users["owner@example.test"]["tenant_id"] = "tenant-b"
    assert client.get(f"/api/graph/{pid}", headers=headers["owner"]).status_code == 404


@pytest.mark.parametrize("flag", ["revoked", "rights_revoked", "deleted"])
def test_current_source_flags_are_checked_with_real_mongo_projection(pipeline_app, flag):
    client, headers, db, _ = pipeline_app
    db.playables.rows[0][flag] = True
    for method, path, body in [("GET", "/api/playable/owned/raw", None),
                               ("PUT", "/api/pipeline/owned/kb/core_specs", {"data": {"logline": "denied"}})]:
        denied = client.request(method, path, headers=headers["owner"], json=body)
        assert denied.status_code == 404, denied.text
    assert db.game_kb.rows == []


def test_inclusion_and_exclusion_projections_preserve_scope_checks(pipeline_app):
    client, headers, db, _ = pipeline_app
    db.game_kb.rows.append({"game_id": "owned", "owner_id": "owner@example.test", "tenant_id": "tenant-a", "_id": "kb-row"})
    router = playable_access.project_router(prefix="/test-projection")
    @router.get("/owned")
    async def projected():
        scoped = playable_access.scoped_database(db)
        return {"inclusion": await scoped.game_kb.find_one({"game_id": "owned"}, {"_id": 1}),
                "exclusion": await scoped.game_kb.find_one({"game_id": "owned"}, {"owner_id": 0, "tenant_id": 0})}
    client.app.include_router(router)
    result = client.get("/test-projection/owned", headers=headers["owner"])
    assert result.status_code == 200 and result.json()["inclusion"]["owner_id"] == "owner@example.test"
    assert result.json()["exclusion"]["game_id"] == "owned"


@pytest.mark.parametrize("path", ["/api/wins/owned/pitch", "/api/playable/owned/cover"])
@pytest.mark.parametrize("revoke", [False, True])
def test_private_model_calls_bind_scope_and_reject_revoked_results(pipeline_app, monkeypatch, path, revoke):
    client, headers, db, users = pipeline_app
    db.playables.rows[0]["brief"] = "OWNER MODEL CANARY"
    calls = []
    class Chat:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def with_model(self, *args):
            return self
        def with_params(self, **kwargs):
            return self
        async def send_message(self, message):
            if revoke:
                users["owner@example.test"]["role"] = "viewer"
            return "OWNER MODEL RESULT"
        async def send_message_multimodal_response(self, message):
            if revoke:
                users["owner@example.test"]["role"] = "viewer"
            return "", [{"data": "image"}]
    monkeypatch.setattr(engine_chat, "EngineChat", Chat)
    monkeypatch.setattr("core.render_quality.upscale_b64", lambda value: value)
    response = client.post(path, headers=headers["owner"])
    assert calls[0]["tenant_id"] == "tenant-a" and calls[0]["actor_id"] == "owner@example.test"
    assert calls[0]["data_class"] == "confidential"
    if revoke:
        assert response.status_code == 403 and "OWNER MODEL RESULT" not in response.text
        assert not db.playables.writes
    else:
        assert response.status_code == 200, response.text


def test_image_cache_key_cannot_collide_on_identity_delimiters(monkeypatch):
    monkeypatch.setattr(image_generation, "project_identity", lambda: {"tenant_id": "a|b", "owner_id": "c"})
    first = image_generation._cache_key("private", "square", "provider")
    monkeypatch.setattr(image_generation, "project_identity", lambda: {"tenant_id": "a", "owner_id": "b|c"})
    assert first != image_generation._cache_key("private", "square", "provider")


def test_mongo_id_inclusion_with_field_exclusion_stays_valid():
    assert playable_access._projection({"_id": 1, "html": 0}) == {"html": 0}
    assert playable_access._projection({"_id": 1, "owner_id": 0}) == {}
    assert playable_access._projection({"_id": 1})["owner_id"] == 1


def test_aggregate_cursor_cannot_be_reused_by_another_authenticated_account(pipeline_app):
    client, headers, db, _ = pipeline_app
    class Summary:
        def aggregate(self, pipeline):
            return Cursor([{"summary": "OWNER AGGREGATE CANARY"}])
    db.tables["private_summary"] = Summary()
    saved = {}
    router = playable_access.project_router(prefix="/test-private-cursor")
    @router.post("/prime")
    async def prime():
        saved["cursor"] = playable_access.scoped_database(db).private_summary.aggregate([])
        return {"ok": True}
    @router.get("/consume")
    async def consume():
        return await saved["cursor"].to_list(1)
    client.app.include_router(router)
    assert client.post("/test-private-cursor/prime", headers=headers["owner"]).status_code == 200
    foreign = client.get("/test-private-cursor/consume", headers=headers["foreign"])
    assert foreign.status_code == 403 and "OWNER AGGREGATE CANARY" not in foreign.text
    own = client.get("/test-private-cursor/consume", headers=headers["owner"])
    assert own.status_code == 200 and "OWNER AGGREGATE CANARY" in own.text


def test_admin_cannot_adopt_foreign_or_legacy_unowned_project(pipeline_app):
    client, headers, db, users = pipeline_app
    users["owner@example.test"]["role"] = "admin"
    db.playables.rows.append({"playable_id": "legacy", "html": "LEGACY SECRET"})
    for pid in ["foreign", "other-tenant", "legacy"]:
        response = client.get(f"/api/playable/{pid}/raw", headers=headers["owner"])
        assert response.status_code == 404 and "SECRET" not in response.text


@pytest.mark.parametrize("source_owner", ["owner@example.test", "foreign@example.test", None])
def test_journey_uses_current_owned_galaxy_side_signals_only(pipeline_app, monkeypatch, source_owner):
    import sys
    import core
    client, headers, db, _ = pipeline_app
    calls = []
    def summary(pid):
        calls.append(pid)
        return {"built_count": 1, "stage_count": 1, "gamefile_count": 2}
    monkeypatch.setitem(sys.modules, "core.stage_builder", SimpleNamespace(summary=summary))
    monkeypatch.setitem(sys.modules, "core.construct_forge", SimpleNamespace(build_assets=lambda pid: ["owned asset"]))
    monkeypatch.setattr(core, "stage_builder", sys.modules["core.stage_builder"], raising=False)
    monkeypatch.setattr(core, "construct_forge", sys.modules["core.construct_forge"], raising=False)
    row = {"build_id": "owned", "tenant_id": "tenant-a"}
    if source_owner:
        row["owner_id"] = source_owner
    db.galaxy_builds.rows.append(row)
    result = client.get("/api/galaxy-studio/journey/owned", headers=headers["owner"])
    assert result.status_code == 200, result.text
    spine = next(item for item in result.json()["milestones"] if item["key"] == "spine")
    assert (spine["state"] == "done") == bool(source_owner == "owner@example.test")
    assert calls == (["owned"] if source_owner == "owner@example.test" else [])
