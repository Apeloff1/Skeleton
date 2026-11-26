"""Creator continuity: closed source data plus actual Mongo revision commits.

Mongo tests use a disposable operator-supplied database and explicitly stub only
the unrelated governed storage-admission response. They never run an engine,
model, compiler, crawler or source-review operation.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Header
from motor.motor_asyncio import AsyncIOMotorClient

from core.dragon_native_projects import (
    DragonCreatorProjects, EXPORT_SCHEMA, SCHEMA, SOURCE_PATH, canonical, validate_document,
)
from core.game_learning import GameLearningError, GameLearningWorkspace, _json, _public


def document():
    return {"schema": SCHEMA, "title": "Original Lantern Quest", "style": "fixed_screen_puzzle",
            "targets": ["pc_linux", "pc_windows"], "seed": 4294967295,
            "portable_design": {"palette": "vga_dusk", "hero": "explorer", "quest_theme": "forest",
                "difficulty": 4, "stages": 1, "candidates": 8,
                "project_notes": "An original branching game", "procedural_levels": False,
                "campaign_pathing": "branching", "challenge_profile": "balanced"},
            "authored_puzzles": [["############", "#..........#", "#..........#", "#..........#",
                "#...@......#", "#....$.....#", "#....o.....#", "#..........#", "#..........#", "############"]],
            "cited_brief": {"text": "Original story: lanterns light the way. α\nA reference is not permission.",
                "citations": [{"source_id": "source-one", "revision_digest": "a" * 64,
                               "title": "Movement reference", "url": "https://example.test/design"}]}}


def test_closed_document_retains_full_unvalidated_authored_source():
    original = document()
    # Unfinished gameplay is valid saved source; source export must revalidate.
    original["authored_puzzles"][0][4] = "#..........#"
    saved = validate_document(original)
    assert saved == original
    assert saved is not original
    assert "approved" not in canonical(saved).decode()


def test_near_limit_admitted_source_always_fits_portable_envelope():
    value = document()
    value["cited_brief"]["citations"] = [{"source_id": "α" * 128, "revision_digest": "a" * 64,
        "title": "🐲" * 200, "url": "https://example.test/" + "x" * 2027} for _ in range(32)]
    value["cited_brief"]["text"] = "🐲" * 12000
    while True:
        try:
            source = validate_document(value)
            break
        except GameLearningError as exc:
            assert exc.code == "creator_document_limit"
            value["cited_brief"]["text"] = value["cited_brief"]["text"][:-64]
    encoded = canonical(source)
    assert len(encoded) > 128 * 1024 - 512
    assert len(canonical({"schema": EXPORT_SCHEMA, "document": source,
                          "document_sha256": sha256(encoded).hexdigest()})) <= 128 * 1024


@pytest.mark.parametrize("change", [
    lambda d: d.update(approved=True),
    lambda d: d.update(owner_id="other"),
    lambda d: d.update(seed=True),
    lambda d: d.update(seed=2**32),
    lambda d: d.update(targets=["pc_linux", "pc_linux"]),
    lambda d: d["portable_design"].update(difficulty=False),
    lambda d: d["portable_design"].update(compile_roms=True),
    lambda d: d["portable_design"].update(stages=2),
    lambda d: d["cited_brief"].update(approved=True),
    lambda d: d["cited_brief"]["citations"][0].update(url="javascript:alert(1)"),
    lambda d: d["cited_brief"]["citations"][0].update(revision_digest="unbound"),
    lambda d: d["cited_brief"].update(text="x" * 12001),
])
def test_invalid_or_authority_bearing_document_is_denied(change):
    value = document(); change(value)
    with pytest.raises(GameLearningError):
        validate_document(value)


@pytest_asyncio.fixture
async def stored():
    path = Path(os.environ.get("SKL_TEST_MONGO_CONFIG", "/workspace/verticals-runtime/mongo.json"))
    if not path.is_file():
        pytest.skip("Actual disposable Mongo config is unavailable; no persistence qualification inferred")
    config = json.loads(path.read_text())
    client = AsyncIOMotorClient(config["uri"], serverSelectionTimeoutMS=3000)
    name = config["database_prefix"] + "_dragon_b_" + uuid4().hex
    database = client[name]
    await database.command("ping")
    authority = GameLearningWorkspace(database)
    admissions = []
    async def admit(scope, resource, write_id, size):
        admissions.append((resource, size))
        return {"storage_bytes": size, "fixture": "storage_admission_only"}
    authority._admit = admit
    authority._recover_jobs = AsyncMock(side_effect=AssertionError("creator reads must not recover jobs"))
    authority._schedule_queued = AsyncMock(side_effect=AssertionError("creator reads must not start jobs"))
    adapter = DragonCreatorProjects(authority)
    scope = {"tenant_id": "creator-tenant", "owner_id": "creator-owner"}
    try:
        yield adapter, authority, scope, database, admissions
    finally:
        await client.drop_database(name)
        client.close()


async def create(adapter, scope, key="first-create", doc=None):
    return await adapter.create(scope, {"idempotency_key": key, "document": doc or document()})


def save_body(project, *, key="save-1", doc=None):
    updated = deepcopy(doc or project["document"])
    if doc is None:
        updated["title"] = "Revised Lantern Quest"
    return {"idempotency_key": key, "expected_version": project["version"],
            "expected_sha256": project["document_sha256"], "document": updated}


@pytest.mark.asyncio
async def test_real_mongo_create_replay_restart_and_committed_initial_history(stored):
    adapter, authority, scope, db, admissions = stored
    first = await create(adapter, scope)
    again = await create(adapter, scope)
    assert again == first
    assert await db.game_learning_projects.count_documents({}) == 1
    assert await db.game_learning_revisions.count_documents({}) == 1
    assert (await db.game_learning_limits.find_one({}))["projects"] == 1
    head = await db.game_learning_projects.find_one({})
    assert next(size for kind, size in admissions if kind == "game-learning-project") >= len(_json(_public(head)))
    # Reconstruct the real authority against the same durable database.
    restarted = DragonCreatorProjects(GameLearningWorkspace(db))
    assert (await restarted.get(scope, first["project_id"]))["document"] == document()
    history = await restarted.history(scope, first["project_id"])
    assert [r["version"] for r in history["revisions"]] == [1]
    assert (await restarted.revision(scope, first["project_id"], 1))["document"] == document()
    assert first["source_only"] is True and first["approval_restored"] is False
    authority._recover_jobs.assert_not_awaited()
    authority._schedule_queued.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_mongo_save_replay_conflict_and_history_restore_as_new_revision(stored):
    adapter, authority, scope, db, _ = stored
    first = await create(adapter, scope)
    request = save_body(first)
    saved = await adapter.save(scope, first["project_id"], request)
    assert saved["version"] == 2
    assert (await adapter.save(scope, first["project_id"], request))["version"] == 2
    assert await db.game_learning_revisions.count_documents({}) == 2
    with pytest.raises(GameLearningError, match="newer project"):
        await adapter.save(scope, first["project_id"], save_body(first, key="stale-client"))
    modified_key = deepcopy(request); modified_key["expected_sha256"] = "f" * 64
    with pytest.raises(GameLearningError) as conflict:
        await adapter.save(scope, first["project_id"], modified_key)
    assert conflict.value.status == 409
    old = await adapter.revision(scope, first["project_id"], 1)
    assert (await adapter.get(scope, first["project_id"]))["version"] == 2
    restored = await adapter.save(scope, first["project_id"], save_body(saved, key="restore-old", doc=old["document"]))
    assert restored["version"] == 3 and restored["document"] == first["document"]
    assert [r["version"] for r in (await adapter.history(scope, first["project_id"]))["revisions"]] == [3, 2, 1]


@pytest.mark.asyncio
async def test_real_mongo_lost_ack_replay_returns_original_commit_after_peer_edit(stored):
    adapter, _, scope, _, _ = stored
    first = await create(adapter, scope)
    original = save_body(first)
    second = await adapter.save(scope, first["project_id"], original)
    newer_doc = deepcopy(second["document"]); newer_doc["title"] = "Peer Revision Quest"
    third = await adapter.save(scope, first["project_id"], save_body(second, key="peer", doc=newer_doc))
    recovered = await adapter.save(scope, first["project_id"], original)
    assert recovered["version"] == 2 and recovered["head_version"] == 3
    assert recovered["document"] == original["document"]
    created_again = await create(adapter, scope)
    assert created_again["version"] == 1 and created_again["head_version"] == 3
    assert created_again["document"] == document()
    assert (await adapter.get(scope, first["project_id"]))["document"] == third["document"]


@pytest.mark.asyncio
async def test_real_mongo_bounded_history_paging_reaches_first_of_more_than_32_revisions(stored):
    adapter, _, scope, _, _ = stored
    head = await create(adapter, scope)
    for i in range(35):
        changed = deepcopy(head["document"]); changed["title"] = "Lantern Edition " + str(i)
        head = await adapter.save(scope, head["project_id"], save_body(head, key="edition-" + str(i), doc=changed))
    newest = await adapter.history(scope, head["project_id"])
    assert len(newest["revisions"]) == 32
    older = await adapter.history(scope, head["project_id"], before_version=newest["next_before_version"])
    versions = [r["version"] for r in newest["revisions"] + older["revisions"]]
    assert versions == list(range(36, 0, -1)) and older["next_before_version"] is None


@pytest.mark.asyncio
async def test_real_mongo_concurrent_creates_and_updates_have_one_winner(stored):
    adapter, _, scope, db, _ = stored
    created = await asyncio.gather(create(adapter, scope), create(adapter, scope), return_exceptions=True)
    first = next(v for v in created if isinstance(v, dict))
    assert await db.game_learning_projects.count_documents({}) == 1
    assert (await db.game_learning_limits.find_one({}))["projects"] == 1
    contenders = await asyncio.gather(
        adapter.save(scope, first["project_id"], save_body(first, key="left")),
        adapter.save(scope, first["project_id"], save_body(first, key="right")), return_exceptions=True)
    assert len([v for v in contenders if isinstance(v, dict)]) == 1
    assert (await adapter.get(scope, first["project_id"]))["version"] == 2


@pytest.mark.asyncio
async def test_real_mongo_scope_isolation_and_stable_portable_export(stored):
    adapter, _, scope, _, _ = stored
    first = await create(adapter, scope)
    for foreign in ({**scope, "owner_id": "other"}, {**scope, "tenant_id": "other"}):
        assert await adapter.list(foreign) == []
        for call in (adapter.get(foreign, first["project_id"]), adapter.export(foreign, first["project_id"]),
                     adapter.history(foreign, first["project_id"])):
            with pytest.raises(GameLearningError) as absent:
                await call
            assert absent.value.status == 404
    payload = await adapter.export(scope, first["project_id"])
    assert payload == await adapter.export(scope, first["project_id"])
    portable = json.loads(payload)
    assert set(portable) == {"schema", "document", "document_sha256"}
    assert portable["schema"] == EXPORT_SCHEMA
    assert portable["document_sha256"] == sha256(canonical(portable["document"])).hexdigest()
    imported = await create(adapter, scope, "import-copy", portable["document"])
    assert imported["project_id"] != first["project_id"]
    assert imported["document_sha256"] == first["document_sha256"]


@pytest.mark.asyncio
async def test_real_mongo_uncommitted_revision_and_tampered_source_are_not_accepted(stored):
    adapter, _, scope, db, _ = stored
    first = await create(adapter, scope)
    row = await db.game_learning_revisions.find_one({"project_id": first["project_id"]})
    row["_id"], row["version"] = "uncommitted", 17
    await db.game_learning_revisions.insert_one(row)
    with pytest.raises(GameLearningError) as absent:
        await adapter.revision(scope, first["project_id"], 17)
    assert absent.value.status == 404
    await db.game_learning_projects.update_one({"_id": first["project_id"]}, {"$set": {"files.0.digest": "0" * 64}})
    with pytest.raises(GameLearningError) as corrupt:
        await adapter.get(scope, first["project_id"])
    assert corrupt.value.code == "creator_source_integrity"


@pytest.mark.asyncio
async def test_real_mongo_denied_admission_leaves_no_published_project(stored):
    adapter, authority, scope, db, _ = stored
    authority._admit = AsyncMock(side_effect=GameLearningError("storage_denied", "Denied", 503))
    with pytest.raises(GameLearningError):
        await create(adapter, scope)
    assert await db.game_learning_projects.count_documents({}) == 0
    assert await db.game_learning_revisions.count_documents({}) == 0


@pytest.mark.asyncio
async def test_actual_http_auth_closed_envelopes_and_mongo_reconnect(stored, monkeypatch):
    adapter, _, _, db, _ = stored
    from routes import dragon_academy as routes
    from core import dragon_native_projects as owner
    app = FastAPI(); app.include_router(routes.router)
    def user(authorization: str | None = Header(default=None)):
        if authorization == "Bearer editor-fixture":
            return {"email": "creator@example.test", "tenant_id": "tenant-http", "role": "editor"}
        if authorization == "Bearer viewer-fixture":
            return {"email": "creator@example.test", "tenant_id": "tenant-http", "role": "viewer"}
        return None
    app.dependency_overrides[routes.get_current_user] = user
    monkeypatch.setattr(owner, "creator_projects", adapter)
    prefix = "/api/dragon-academy/native/production/projects"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(prefix)).status_code == 401
        body = {"idempotency_key": "http-create", "document": document()}
        assert (await client.post(prefix, json=body, headers={"Authorization": "Bearer viewer-fixture"})).status_code == 403
        headers = {"Authorization": "Bearer editor-fixture"}
        assert (await client.post(prefix, json={**body, "tenant_id": "injected"}, headers=headers)).status_code == 422
        made = await client.post(prefix, json=body, headers=headers)
        assert made.status_code == 201, made.text
        assert made.headers["cache-control"] == "private, no-store"
        assert "Authorization" in made.headers["vary"]
        project = made.json()["project"]
        owned = await db.game_learning_projects.find_one({"project_id": project["project_id"]})
        assert owned["owner_id"] == "creator@example.test" and owned["tenant_id"] == "tenant-http"
        assert (await db.game_learning_limits.find_one({"owner_id": "creator@example.test"}))["projects"] == 1
        for suffix in ("", "/" + project["project_id"], "/" + project["project_id"] + "/history",
                       "/" + project["project_id"] + "/history/1"):
            response = await client.get(prefix + suffix, headers=headers)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "private, no-store"
            assert "Authorization" in response.headers["vary"]
        archive = await client.get(prefix + "/" + project["project_id"] + "/export", headers=headers)
        assert archive.status_code == 200
        assert archive.headers["x-content-sha256"] == sha256(archive.content).hexdigest()
        assert "attachment" in archive.headers["content-disposition"]
        assert archive.headers["cache-control"] == "private, no-store" and "Authorization" in archive.headers["vary"]
    # New application and authority objects, same actual Mongo bytes.
    monkeypatch.setattr(owner, "creator_projects", DragonCreatorProjects(GameLearningWorkspace(db)))
    restarted = FastAPI(); restarted.include_router(routes.router)
    restarted.dependency_overrides[routes.get_current_user] = user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url="http://test") as client:
        reopened = await client.get(prefix + "/" + project["project_id"], headers=headers)
        assert reopened.status_code == 200 and reopened.json()["project"]["document"] == document()
