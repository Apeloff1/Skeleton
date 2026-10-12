"""Project-scoped, authenticated story reference index for Jeeves.

Separate append-only Mongo records avoid the 16MB document ceiling of the
canonical game KB. This is an evidence ledger, *not* a second conversation
authority or an automatic canon/model-weight promotion endpoint.

POST is creator-reviewed only, role-gated and idempotent. GET/audit/recall are
bounded projections over the current user's project and a single story branch.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.story_continuity import (
    EVENT_KINDS, MAX_EVENTS_PER_AUDIT, MAX_STREAM_EVENTS,
    StoryAuditAccumulator, event_digest, recall_context,
)
from routes.gameforge_auth import require_role
from routes.playable import _db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Jeeves story continuity"])
_ID_PATTERN = r"^[A-Za-z0-9:_-]{1,96}$"
_GAME_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class StoryEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_id: str = Field(min_length=1, max_length=96, pattern=_ID_PATTERN)
    branch_id: str = Field(default="main", pattern=_ID_PATTERN)
    act: int = Field(ge=1, le=10000)
    scene: int = Field(ge=1, le=100000)
    beat: int = Field(ge=0, le=100000)
    kind: str = Field(max_length=32)
    character_ids: list[str] = Field(default_factory=list, max_length=12)
    speaker_id: str | None = Field(default=None, max_length=96)
    witness_ids: list[str] = Field(default_factory=list, max_length=12)
    text: str = Field(min_length=1, max_length=4000)
    knowledge_required: list[str] = Field(default_factory=list, max_length=20)
    knowledge_granted: list[str] = Field(default_factory=list, max_length=20)
    thread_key: str | None = Field(default=None, max_length=96)
    source_thread_id: str | None = Field(default=None, max_length=96)
    source_message_id: str | None = Field(default=None, max_length=96)

    @model_validator(mode="after")
    def validate_relationships(self):
        if self.kind not in EVENT_KINDS:
            raise ValueError("Unknown story event kind")
        values = [
            *self.character_ids, *self.witness_ids,
            *self.knowledge_required, *self.knowledge_granted,
        ]
        values += [
            x for x in (
                self.speaker_id, self.thread_key,
                self.source_thread_id, self.source_message_id,
            ) if x is not None
        ]
        if any(not re.fullmatch(_ID_PATTERN, x) for x in values):
            raise ValueError("Identifiers must be stable ASCII slugs")
        for field in (
            self.character_ids, self.witness_ids,
            self.knowledge_required, self.knowledge_granted,
        ):
            if len(set(field)) != len(field):
                raise ValueError("Duplicate identifiers are not allowed")
        if not set(self.witness_ids).issubset(self.character_ids):
            raise ValueError("Witnesses must be event participants")
        if self.speaker_id and self.speaker_id not in self.character_ids:
            raise ValueError("Speaker must participate")
        if self.kind == "dialogue" and not self.speaker_id:
            raise ValueError("Dialogue must identify speaker")
        if self.kind in {"promise", "resolution"} and not self.thread_key:
            raise ValueError("Story promise/resolution must identify thread")
        if self.kind in {"death", "revival"} and not self.character_ids:
            raise ValueError("Life events must identify affected characters")
        if any(ord(c) < 32 and c not in "\t\n" for c in self.text):
            raise ValueError("Story text contains unsupported control characters")
        return self


def _scope(pid: str, user: dict) -> dict[str, str]:
    if not _GAME_ID.fullmatch(pid):
        raise HTTPException(status_code=422, detail="Invalid game ID")
    tenant = str(user.get("tenant_id") or "default")
    owner = str(user.get("email") or user.get("user_id") or "")
    if not owner or not re.fullmatch(r"[A-Za-z0-9@._+\-]{1,254}", owner):
        raise HTTPException(status_code=401, detail="Author identity unavailable")
    return {"game_id": pid, "tenant_id": tenant, "owner_id": owner}


def _entry_id(scope: dict[str, str], event: StoryEventIn) -> str:
    # Atomic idempotency lives in Mongo _id, not a preflight SELECT alone.
    text = "|".join((scope["tenant_id"], scope["owner_id"], scope["game_id"],
                     event.branch_id, event.event_id))
    return sha256(text.encode("utf-8")).hexdigest()


def _public(doc: dict) -> dict:
    return {
        key: value for key, value in doc.items()
        if key not in {"_id", "owner_id", "tenant_id", "payload_digest"}
    }


async def _ensure_story_indexes() -> None:
    # Creates are idempotent. The scoped compound index supports bounded
    # chronological paging and per-character multikey lookups.
    await _db.game_story_events.create_index([
        ("tenant_id", ASCENDING), ("owner_id", ASCENDING),
        ("game_id", ASCENDING), ("branch_id", ASCENDING),
        ("act", ASCENDING), ("scene", ASCENDING),
        ("beat", ASCENDING), ("event_id", ASCENDING),
    ], name="story_by_scene_v1")
    await _db.game_story_events.create_index([
        ("tenant_id", ASCENDING), ("owner_id", ASCENDING),
        ("game_id", ASCENDING), ("branch_id", ASCENDING),
        ("character_ids", ASCENDING),
    ], name="story_by_character_v1")


@router.post("/{pid}/story-index/events")
async def append_story_event(
    pid: str, event: StoryEventIn,
    user=Depends(require_role("editor")),
):
    scope = _scope(pid, user)
    try:
        # Do not create story state for a nonexistent canonical game KB.
        exists = await _db.game_kb.find_one({"game_id": pid}, {"_id": 1})
        if not exists:
            raise HTTPException(status_code=404, detail="Create the game KB before recording story history")
        await _ensure_story_indexes()
        data = event.model_dump()
        entry_id = _entry_id(scope, event)
        digest = event_digest(data)
        document = {
            "_id": entry_id, **scope, **data, "payload_digest": digest,
            "record_status": "creator_reviewed_evidence",
            "source_integrity": "creator_supplied_not_independently_verified",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await _db.game_story_events.insert_one(document)
            replayed = False
        except DuplicateKeyError:
            current = await _db.game_story_events.find_one({"_id": entry_id, **scope})
            if not current or current.get("payload_digest") != digest:
                raise HTTPException(
                    status_code=409,
                    detail="Story event identity was already used for different content",
                )
            document = current
            replayed = True
        return {
            "ok": True, "event": _public(document), "replayed": replayed,
            "receipt": entry_id,
        }
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        logger.exception("story index database write unavailable")
        raise HTTPException(status_code=503, detail="Story index storage unavailable")


@router.get("/{pid}/story-index/events")
async def list_story_events(
    pid: str,
    branch_id: str = Query("main", pattern=_ID_PATTERN),
    character_id: str | None = Query(None, pattern=_ID_PATTERN),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=50000),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    query = {**scope, "branch_id": branch_id}
    if character_id:
        query["character_ids"] = character_id
    try:
        docs = await (
            _db.game_story_events.find(query, {"owner_id": 0, "tenant_id": 0, "payload_digest": 0})
            .sort([("act", ASCENDING), ("scene", ASCENDING), ("beat", ASCENDING), ("event_id", ASCENDING)])
            .skip(offset).limit(limit + 1).to_list(length=limit + 1)
        )
    except (PyMongoError, OSError):
        logger.exception("story index read unavailable")
        raise HTTPException(status_code=503, detail="Story index storage unavailable")
    more = len(docs) > limit
    return {
        "ok": True, "game_id": pid, "branch_id": branch_id,
        "character_id": character_id, "events": [_public(d) for d in docs[:limit]],
        "next_offset": offset + limit if more else None,
        "partial": more or offset > 0,
    }


async def _recent_character_events(
    scope: dict, branch_id: str, character_id: str,
) -> tuple[list[dict], bool]:
    # Read the most recent *character-specific* events, not the first 2,000
    # events in the entire world. Earlier scenes remain discoverable with
    # pagination; a truncated recall is explicitly labelled incomplete.
    docs = await (
        _db.game_story_events.find({
            **scope, "branch_id": branch_id, "character_ids": character_id,
        })
        .sort([
            ("act", -1), ("scene", -1), ("beat", -1), ("event_id", -1),
        ])
        .limit(MAX_EVENTS_PER_AUDIT + 1)
        .to_list(length=MAX_EVENTS_PER_AUDIT + 1)
    )
    complete = len(docs) <= MAX_EVENTS_PER_AUDIT
    return docs[:MAX_EVENTS_PER_AUDIT], complete


@router.get("/{pid}/story-index/audit")
async def audit_story_index(
    pid: str,
    branch_id: str = Query("main", pattern=_ID_PATTERN),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    try:
        accumulator = StoryAuditAccumulator(bookmark_limit=100)
        cursor = _db.game_story_events.find({**scope, "branch_id": branch_id}).sort([
            ("act", ASCENDING), ("scene", ASCENDING),
            ("beat", ASCENDING), ("event_id", ASCENDING),
        ])
        complete = True
        async for entry in cursor:
            if accumulator.event_count >= MAX_STREAM_EVENTS:
                complete = False
                break
            accumulator.ingest(entry)
        report = accumulator.finish(complete=complete)
    except (PyMongoError, OSError):
        logger.exception("story audit read unavailable")
        raise HTTPException(status_code=503, detail="Story index storage unavailable")
    return {"ok": True, "game_id": pid, "branch_id": branch_id, "audit": report}


@router.get("/{pid}/story-index/recall/{character_id}")
async def recall_story_character(
    pid: str, character_id: str,
    branch_id: str = Query("main", pattern=_ID_PATTERN),
    max_chars: int = Query(4000, ge=128, le=12000),
    user=Depends(require_role("viewer")),
):
    if not re.fullmatch(_ID_PATTERN, character_id):
        raise HTTPException(status_code=422, detail="Invalid character ID")
    scope = _scope(pid, user)
    try:
        events, complete = await _recent_character_events(scope, branch_id, character_id)
        recall = recall_context(events, character_id, branch_id=branch_id,
                                limit_chars=max_chars, complete=complete)
    except (PyMongoError, OSError):
        logger.exception("story recall read unavailable")
        raise HTTPException(status_code=503, detail="Story recall storage unavailable")
    return {"ok": True, "game_id": pid, "recall": recall}
