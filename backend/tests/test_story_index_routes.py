"""Deterministic in-memory Mongo contract tests for the story index API."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, OperationFailure

from routes import story_index as route

ACTOR = {"email": "author@example.com", "role": "admin", "tenant_id": "team-a"}
OTHER = {"email": "other@example.com", "role": "admin", "tenant_id": "team-a"}


def row(event_id="witness-1", **overrides):
    data = {
        "event_id": event_id, "branch_id": "main", "act": 1, "scene": 1,
        "beat": 1, "kind": "witness", "character_ids": ["hero", "guard"],
        "speaker_id": None, "witness_ids": ["guard"],
        "text": "The guard sees the hero open the ancient gate.",
        "knowledge_required": [], "knowledge_granted": ["gate_open"],
        "thread_key": None, "source_thread_id": "jeeves-thread-2",
        "source_message_id": "jeeves-message-9",
    }
    return route.StoryEventIn(**{**data, **overrides})


class Cursor:
    def __init__(self, documents):
        self.documents = list(documents)
        self.off = 0
        self.max = None

    def sort(self, keys):
        self.documents.sort(key=lambda doc: tuple(doc.get(key, "") for key, _ in keys))
        return self

    def skip(self, offset):
        self.off = offset
        return self

    def limit(self, amount):
        self.max = amount
        return self

    async def to_list(self, *, length):
        rows = self.documents[self.off:]
        if self.max is not None:
            rows = rows[:self.max]
        return deepcopy(rows[:length])


class StoryCollection:
    def __init__(self):
        self.rows = {}
        self.indexes = []

    async def create_index(self, keys, *, name):
        self.indexes.append(name)
        return name

    async def insert_one(self, document):
        key = document["_id"]
        if key in self.rows:
            raise DuplicateKeyError("duplicate story identity")
        self.rows[key] = deepcopy(document)

    async def find_one(self, match):
        for item in self.rows.values():
            if all(item.get(k) == v for k, v in match.items()):
                return deepcopy(item)
        return None

    def find(self, query, projection=None):
        def eligible(item):
            for key, value in query.items():
                if key == "character_ids":
                    if value not in item.get(key, []):
                        return False
                elif item.get(key) != value:
                    return False
            return True
        return Cursor(d for d in self.rows.values() if eligible(d))


class GameCollection:
    def __init__(self, enabled=True):
        self.enabled = enabled

    async def find_one(self, query, projection=None):
        return {"_id": "game"} if self.enabled else None


@pytest.fixture
def database(monkeypatch):
    story = StoryCollection()
    game = GameCollection()
    monkeypatch.setattr(route, "_db", SimpleNamespace(
        game_story_events=story, game_kb=game,
    ))
    return story, game


@pytest.mark.asyncio
async def test_append_records_scoped_immutable_evidence_and_creates_indexes(database):
    stories, _ = database
    result = await route.append_story_event("game-1", row(), user=ACTOR)
    assert result["ok"] is True
    assert result["replayed"] is False
    assert len(result["receipt"]) == 64
    assert result["event"]["record_status"] == "creator_reviewed_evidence"
    assert result["event"]["source_integrity"] == "creator_supplied_not_independently_verified"
    assert "owner_id" not in result["event"]
    assert "payload_digest" not in result["event"]
    assert len(stories.rows) == 1
    assert stories.indexes == ["story_by_scene_v1", "story_by_character_v1"]


@pytest.mark.asyncio
async def test_exact_retry_replays_and_identity_reuse_with_changed_content_conflicts(database):
    stories, _ = database
    original = await route.append_story_event("game-1", row(), user=ACTOR)
    repeated = await route.append_story_event("game-1", row(), user=ACTOR)
    assert repeated["replayed"] is True
    assert repeated["receipt"] == original["receipt"]
    assert len(stories.rows) == 1
    with pytest.raises(HTTPException) as error:
        await route.append_story_event("game-1", row(text="Changed on retry"), user=ACTOR)
    assert error.value.status_code == 409
    assert len(stories.rows) == 1


@pytest.mark.asyncio
async def test_cross_user_and_tenant_isolation_even_for_reused_event_ids(database):
    stories, _ = database
    author = await route.append_story_event("game-1", row(), user=ACTOR)
    different = await route.append_story_event("game-1", row(), user=OTHER)
    assert author["receipt"] != different["receipt"]
    assert len(stories.rows) == 2
    our_events = await route.list_story_events("game-1", branch_id="main",
                  character_id=None, limit=100, offset=0, user=ACTOR)
    assert len(our_events["events"]) == 1


@pytest.mark.asyncio
async def test_story_index_requires_an_existing_canonical_game(database):
    stories, game = database
    game.enabled = False
    with pytest.raises(HTTPException) as error:
        await route.append_story_event("missing", row(), user=ACTOR)
    assert error.value.status_code == 404
    assert not stories.rows


@pytest.mark.asyncio
async def test_ordered_branch_pagination_and_character_filtering(database):
    for index in [4, 3, 1, 2]:
        await route.append_story_event(
            "game-1",
            row(f"event-{index}", scene=index,
                character_ids=["hero", "guard"] if index % 2 == 0 else ["hero"],
                witness_ids=["guard"] if index % 2 == 0 else []),
            user=ACTOR,
        )
    first = await route.list_story_events(
        "game-1", branch_id="main", character_id=None, limit=2,
        offset=0, user=ACTOR)
    assert [e["event_id"] for e in first["events"]] == ["event-1", "event-2"]
    assert first["next_offset"] == 2
    second = await route.list_story_events(
        "game-1", branch_id="main", character_id=None, limit=2,
        offset=2, user=ACTOR)
    assert [e["event_id"] for e in second["events"]] == ["event-3", "event-4"]
    assert second["next_offset"] is None
    filtered = await route.list_story_events(
        "game-1", branch_id="main", character_id="guard", limit=10,
        offset=0, user=ACTOR)
    assert [e["event_id"] for e in filtered["events"]] == ["event-2", "event-4"]


@pytest.mark.asyncio
async def test_full_audit_and_recall_use_provenance_across_distant_scenes(database):
    await route.append_story_event("game-1", row(
        "first", kind="discovery", scene=1,
        knowledge_granted=["gate_open"],
    ), user=ACTOR)
    await route.append_story_event("game-1", row(
        "later", kind="dialogue", scene=500,
        speaker_id="hero", knowledge_required=["gate_open"],
        knowledge_granted=[],
    ), user=ACTOR)
    audited = await route.audit_story_index(
        "game-1", branch_id="main", user=ACTOR)
    assert audited["audit"]["valid"] is True
    assert audited["audit"]["event_count"] == 2
    recall = await route.recall_story_character(
        "game-1", "hero", branch_id="main", max_chars=1200, user=ACTOR)
    assert recall["recall"]["included"] == 2
    assert "A1/S500/B1" in recall["recall"]["context"]
    assert "message-later" not in recall["recall"]["context"]  # stored source is explicit
    assert "source:jeeves-message-9" in recall["recall"]["context"]


@pytest.mark.asyncio
async def test_database_outage_is_fail_closed_with_no_success_receipt(database):
    stories, _ = database

    async def fail_write(_):
        raise OperationFailure("storage unavailable", code=1)

    stories.insert_one = fail_write
    with pytest.raises(HTTPException) as error:
        await route.append_story_event("game-1", row(), user=ACTOR)
    assert error.value.status_code == 503


@pytest.mark.parametrize("bad", [
    {"kind": "unknown"},
    {"speaker_id": "outsider", "kind": "dialogue"},
    {"kind": "dialogue"},
    {"witness_ids": ["outsider"]},
    {"knowledge_required": ["repeat", "repeat"]},
    {"kind": "promise", "thread_key": None},
    {"kind": "revival", "character_ids": []},
    {"event_id": "../evil"},
    {"act": -1},
    {"scene": 100001},
    {"text": "bad\x00control"},
])
def test_event_payloads_are_rejected_before_any_database_mutation(bad):
    with pytest.raises(ValidationError):
        row(**bad)


def test_id_scope_refuses_path_injection_and_missing_identity():
    with pytest.raises(HTTPException) as error:
        route._scope("../foreign", ACTOR)
    assert error.value.status_code == 422
    with pytest.raises(HTTPException) as error:
        route._scope("game-1", {"role": "admin"})
    assert error.value.status_code == 401
