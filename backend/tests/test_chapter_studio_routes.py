"""In-memory Mongo contract suite for chapter editor and production routes."""
from __future__ import annotations
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, OperationFailure

from routes import chapter_studio as route

AUTHOR = {"email": "writer@example.com", "tenant_id": "game-team", "role": "editor"}
OTHER = {"email": "other@example.com", "tenant_id": "game-team", "role": "editor"}


def matches(doc, query):
    for k, expected in query.items():
        cursor = doc
        for segment in k.split("."):
            cursor = cursor.get(segment) if isinstance(cursor, dict) else None
        if isinstance(expected, dict) and "$lt" in expected:
            if cursor is None or cursor >= expected["$lt"]:
                return False
        elif cursor != expected:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = deepcopy(list(rows))
        self.offset = 0
        self.maximum = None

    def sort(self, key, direction=None):
        fields = key if isinstance(key, list) else [(key, direction)]
        self.rows.sort(key=lambda x: tuple(x.get(k, "") for k, _ in fields),
                       reverse=all(direction < 0 for _, direction in fields))
        return self

    def skip(self, amount):
        self.offset = amount
        return self

    def limit(self, amount):
        self.maximum = amount
        return self

    async def to_list(self, *, length):
        items = self.rows[self.offset:]
        if self.maximum is not None:
            items = items[:self.maximum]
        return deepcopy(items[:length])

    def __aiter__(self):
        async def iterate():
            for item in await self.to_list(length=len(self.rows)):
                yield item
        return iterate()


class Collection:
    def __init__(self):
        self.docs = {}

    async def find_one(self, query, projection=None):
        return next((deepcopy(doc) for doc in self.docs.values()
                     if matches(doc, query)), None)

    def find(self, query, projection=None):
        return Cursor(doc for doc in self.docs.values() if matches(doc, query))

    async def insert_one(self, doc):
        if doc["_id"] in self.docs:
            raise DuplicateKeyError("duplicate key")
        self.docs[doc["_id"]] = deepcopy(doc)

    async def replace_one(self, query, doc):
        for key, candidate in self.docs.items():
            if matches(candidate, query):
                self.docs[key] = deepcopy(doc)
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def update_one(self, query, change):
        for key, candidate in self.docs.items():
            if matches(candidate, query):
                doc = deepcopy(candidate)
                for field, value in change.get("$set", {}).items():
                    parts = field.split(".")
                    nested = doc
                    for segment in parts[:-1]:
                        nested = nested.setdefault(segment, {})
                    nested[parts[-1]] = deepcopy(value)
                self.docs[key] = doc
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


class GameKB:
    async def find_one(self, query, projection=None):
        return {"_id": "existing_game"} if query.get("game_id") == "game-x" else None


@pytest.fixture
def db(monkeypatch):
    fake = SimpleNamespace(
        game_kb=GameKB(),
        game_story_chapters=Collection(),
        game_story_scenes=Collection(),
        game_story_events=Collection(),
    )
    monkeypatch.setattr(route, "_db", fake)
    return fake


def chapter(**changes):
    source = dict(
        expected_revision=0, branch_id="main",
        title="Origins", synopsis="The king hides a key in the castle.",
        notes="The dragon is believed to be dead.",
        historical_setting="Invented bronze-iron transition",
        palette_rules="Copper, umber and dusk blue",
        costume_rules="Keep the scar on the right eyebrow",
        voice_rules="Never replace Aria's original voice model",
        era_id="iron", style_id="illuminated", palette_id="copper",
        voice_cast={"aria": "voice_original"},
        face_cast={"aria": "face_scar_right"},
        transition_reason=None, source_message_id="jeeves-1",
    )
    source.update(changes)
    return route.ChapterIn(**source)


def scene(chapter_receipt, **changes):
    source = dict(
        expected_revision=0, branch_id="main", chapter=1, act=1,
        summary="Aria sees the locked gate.",
        text="Aria sees the locked gate and remembers the king.",
        characters=["aria"], thread_keys=["lost_key"],
        plot_points=[
            {"id": "gate_01", "kind": "setup",
             "anchor": "locked gate", "description": "Establish the door"},
            {"id": "scar_01", "kind": "visual_identity",
             "anchor": "remembers the king", "description": "History callback"},
        ],
        chapter_revision=chapter_receipt["revision"],
        chapter_digest=chapter_receipt["digest"],
        source_message_id="chat-scene-01",
    )
    source.update(changes)
    return route.SceneIn(**source)


@pytest.mark.asyncio
async def test_chapter_receipt_revision_replay_and_changed_content_conflict(db):
    first = await route.save_chapter("game-x", 1, chapter(), user=AUTHOR)
    assert first["ok"] and first["chapter"]["revision"] == 1
    assert first["replayed"] is False
    assert len(first["receipt"]) == 64
    repeated = await route.save_chapter("game-x", 1, chapter(), user=AUTHOR)
    assert repeated["replayed"] is True
    assert repeated["receipt"] == first["receipt"]
    with pytest.raises(HTTPException) as error:
        await route.save_chapter("game-x", 1, chapter(title="New title"), user=AUTHOR)
    assert error.value.status_code == 409
    changed = await route.save_chapter("game-x", 1,
        chapter(expected_revision=1, title="New title"), user=AUTHOR)
    assert changed["chapter"]["revision"] == 2
    assert changed["receipt"] != first["receipt"]


@pytest.mark.asyncio
async def test_voice_id_locked_both_within_a_chapter_and_across_100_chapters(db):
    first = await route.save_chapter("game-x", 1, chapter(), user=AUTHOR)
    with pytest.raises(HTTPException, match="voice_cast identity"):
        await route.save_chapter("game-x", 1,
            chapter(expected_revision=1, voice_cast={"aria": "replacement"}),
            user=AUTHOR)
    with pytest.raises(HTTPException, match="voice_cast identity"):
        await route.save_chapter("game-x", 2,
            chapter(voice_cast={"aria": "replacement"}), user=AUTHOR)
    allowed = await route.save_chapter("game-x", 2,
        chapter(voice_cast={"aria": "voice_original"}), user=AUTHOR)
    assert allowed["ok"] and first["chapter"]["voice_cast"]["aria"] == "voice_original"


@pytest.mark.asyncio
async def test_facial_identity_and_voice_can_never_change_on_a_forked_branch(db):
    await route.save_chapter("game-x", 1, chapter(), user=AUTHOR)
    with pytest.raises(HTTPException, match="voice_cast identity"):
        await route.save_chapter("game-x", 1,
            chapter(branch_id="alternate", voice_cast={"aria": "replacement"}),
            user=AUTHOR)
    with pytest.raises(HTTPException, match="face_cast identity"):
        await route.save_chapter("game-x", 2,
            chapter(branch_id="alternate", face_cast={"aria": "no_scar"}),
            user=AUTHOR)


@pytest.mark.asyncio
async def test_style_era_and_palette_migration_requires_explicit_reason(db):
    await route.save_chapter("game-x", 1, chapter(), user=AUTHOR)
    with pytest.raises(HTTPException, match="transition"):
        await route.save_chapter("game-x", 2,
            chapter(palette_id="snow"), user=AUTHOR)
    transitioned = await route.save_chapter("game-x", 2,
        chapter(palette_id="snow",
                transition_reason="Act 11 crosses to a new climate zone"),
        user=AUTHOR)
    assert transitioned["chapter"]["transition_reason"]


@pytest.mark.asyncio
async def test_scene_is_bound_to_current_chapter_and_voice_cast(db):
    ch = (await route.save_chapter("game-x", 1, chapter(), user=AUTHOR))["chapter"]
    with pytest.raises(HTTPException, match="voice"):
        await route.save_scene("game-x", 1,
            scene(ch, characters=["unknown"]), user=AUTHOR)
    with pytest.raises(HTTPException, match="Chapter notes"):
        await route.save_scene("game-x", 1,
            scene({**ch, "digest": "f" * 64}), user=AUTHOR)
    value = await route.save_scene("game-x", 1, scene(ch), user=AUTHOR)
    assert value["ok"] and value["scene"]["revision"] == 1
    assert value["scene"]["chapter_digest"] == ch["digest"]
    assert value["scene"]["status"] == "draft"
    assert (await route.save_scene("game-x", 1, scene(ch), user=AUTHOR))["replayed"]


@pytest.mark.asyncio
async def test_full_chapter_scene_context_cites_script_receipts(db):
    ch = (await route.save_chapter("game-x", 1, chapter(), user=AUTHOR))["chapter"]
    draft = (await route.save_scene("game-x", 1, scene(ch), user=AUTHOR))["scene"]
    context = await route.get_chapter_context(
        "game-x", 1, branch_id="main", max_chars=5000, user=AUTHOR)
    assert context["context"]["complete_source"] is True
    assert context["context"]["citations"][0]["receipt"] == draft["digest"]
    assert context["context"]["chapter_digest"] == ch["digest"]
    detail = await route.get_scene("game-x", 1, branch_id="main", user=AUTHOR)
    assert detail["scene"]["source_message_id"] == "chat-scene-01"
    assert [x["id"] for x in detail["highlights"]] == ["gate_01", "scar_01"]


@pytest.mark.asyncio
async def test_100k_inspection_produces_confirmed_proof_and_human_approval(db):
    ch = (await route.save_chapter("game-x", 1, chapter(), user=AUTHOR))["chapter"]
    staged = (await route.save_scene("game-x", 1, scene(ch), user=AUTHOR))["scene"]
    result = await route.proofread_scene("game-x", 1, branch_id="main", user=AUTHOR)
    proof = result["proof"]
    assert result["scene_receipt"] == staged["digest"]
    assert proof["inspections_executed"] == 100000
    assert proof["status"] == "machine_checks_passed"
    signed = await route.approve_scene("game-x", 1,
        route.ApproveSceneIn(proof_digest=proof["receipt_digest"],
                             expected_revision=staged["revision"]), user=AUTHOR)
    assert signed["status"] == "approved_for_production"
    assert "Narrative approval only" in signed["production_note"]
    assert (await route.approve_scene("game-x", 1,
        route.ApproveSceneIn(proof_digest=proof["receipt_digest"],
                             expected_revision=staged["revision"]), user=AUTHOR))["replayed"]
    with pytest.raises(HTTPException, match="immutable"):
        await route.save_scene("game-x", 1,
            scene(ch, expected_revision=1, summary="Rewrite history"), user=AUTHOR)
    with pytest.raises(HTTPException, match="Fork"):
        await route.save_chapter("game-x", 1,
            chapter(expected_revision=1, notes="Change the stable scar"), user=AUTHOR)


@pytest.mark.asyncio
async def test_predecessor_chain_blocks_missing_or_unapproved_scenes(db):
    ch = (await route.save_chapter("game-x", 1, chapter(), user=AUTHOR))["chapter"]
    staged2 = (await route.save_scene("game-x", 2, scene(ch), user=AUTHOR))["scene"]
    reviewed = await route.proofread_scene("game-x", 2, branch_id="main", user=AUTHOR)
    assert "previous_scene_missing" in reviewed["proof"]["blocking_issues"]
    with pytest.raises(HTTPException, match="Proof expired"):
        await route.approve_scene("game-x", 2, route.ApproveSceneIn(
            expected_revision=staged2["revision"],
            proof_digest=reviewed["proof"]["receipt_digest"]), user=AUTHOR)


@pytest.mark.asyncio
async def test_project_and_user_scopes_prevent_cross_editor_read_or_mutation(db):
    ch = (await route.save_chapter("game-x", 1, chapter(), user=AUTHOR))["chapter"]
    result = await route.list_chapters("game-x", branch_id="main", user=OTHER)
    assert result["count"] == 0
    with pytest.raises(HTTPException) as error:
        await route.get_chapter_context(
            "game-x", 1, branch_id="main", max_chars=6000, user=OTHER)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await route.save_scene("game-x", 1, scene(ch), user=OTHER)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_story_index_and_chapter_timeline_branch_isolation(db):
    first = await route.save_chapter("game-x", 1, chapter(), user=AUTHOR)
    branch = await route.save_chapter("game-x", 1,
        chapter(branch_id="alternate", voice_cast={"aria": "voice_original"}),
        user=AUTHOR)
    assert branch["chapter"]["branch_id"] != first["chapter"]["branch_id"]
    assert (await route.list_chapters(
        "game-x", branch_id="main", user=AUTHOR))["count"] == 1
    assert (await route.list_chapters(
        "game-x", branch_id="alternate", user=AUTHOR))["count"] == 1


@pytest.mark.parametrize("change", [
    {"plot_points": []},
    {"characters": []},
    {"plot_points": [{"id": "dup", "kind": "reveal", "anchor": "locked gate"},
                     {"id": "dup", "kind": "setup", "anchor": "remembers the king"}]},
    {"plot_points": [{"id": "bad", "kind": "reveal", "anchor": "unmentioned dragon"}]},
    {"act": 11},
    {"text": "\x00"},
])
def test_scene_editor_rejects_invalid_plots_characters_and_context(change):
    ch = {"revision": 1, "digest": "a" * 64}
    with pytest.raises(ValidationError):
        scene(ch, **change)


@pytest.mark.asyncio
async def test_nonexistent_canonical_game_rejected(db):
    with pytest.raises(HTTPException) as error:
        await route.save_chapter("wrong-game", 1, chapter(), user=AUTHOR)
    assert error.value.status_code == 404
