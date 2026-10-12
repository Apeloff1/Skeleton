"""Jeeves chapter editor / production approval routes.

Bounded, authenticated and provenance-linked editorial operations. Separate
immutable receipts track which chapter note revision and reviewed script were
inspected. Production approval means *narrative editorial approval* and never
claims that scene rendering/voice acting/game packaging happened.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.chapter_continuity import (
    MAX_CHAPTERS, MAX_SCENES, MAX_STREAM_EVENTS, PLOT_KINDS,
    chapter_context, chapter_for_act, digest, plot_spans,
    proofreading_checks, scene_coordinates,
)
from core.story_continuity import StoryAuditAccumulator
from routes.gameforge_auth import require_role
from routes.playable import _db
from routes.story_index import _scope

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Jeeves chapter production"])
SLUG = r"^[A-Za-z0-9:_-]{1,96}$"


class PlotPointIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(pattern=SLUG)
    kind: str
    anchor: str = Field(min_length=2, max_length=500)
    description: str = Field(default="", max_length=600)
    related_event_id: str | None = Field(default=None, pattern=SLUG)

    @model_validator(mode="after")
    def category(self):
        if self.kind not in PLOT_KINDS:
            raise ValueError("Unrecognized plot-point category")
        return self


class ChapterIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(default=0, ge=0)
    branch_id: str = Field(default="main", pattern=SLUG)
    title: str = Field(min_length=1, max_length=180)
    synopsis: str = Field(min_length=1, max_length=3000)
    notes: str = Field(default="", max_length=8000)
    historical_setting: str = Field(min_length=1, max_length=600)
    palette_rules: str = Field(min_length=1, max_length=600)
    costume_rules: str = Field(min_length=1, max_length=600)
    voice_rules: str = Field(min_length=1, max_length=600)
    era_id: str = Field(pattern=SLUG)
    style_id: str = Field(pattern=SLUG)
    palette_id: str = Field(pattern=SLUG)
    voice_cast: dict[str, str] = Field(default_factory=dict, max_length=200)
    transition_reason: str | None = Field(default=None, max_length=1200)
    source_message_id: str | None = Field(default=None, pattern=SLUG)

    @model_validator(mode="after")
    def characters(self):
        for character, voice in self.voice_cast.items():
            if not re.fullmatch(SLUG, character) or not re.fullmatch(SLUG, voice):
                raise ValueError("Character and immutable voice reference must be a slug")
        return self


class SceneIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(default=0, ge=0)
    branch_id: str = Field(default="main", pattern=SLUG)
    chapter: int = Field(ge=1, le=MAX_CHAPTERS)
    act: int = Field(ge=1, le=1000)
    summary: str = Field(min_length=1, max_length=600)
    text: str = Field(min_length=1, max_length=16000)
    characters: list[str] = Field(default_factory=list, min_length=1, max_length=30)
    thread_keys: list[str] = Field(default_factory=list, max_length=100)
    plot_points: list[PlotPointIn] = Field(default_factory=list, min_length=1, max_length=200)
    chapter_revision: int = Field(ge=1)
    chapter_digest: str = Field(min_length=64, max_length=64, pattern="^[a-f0-9]{64}$")
    source_message_id: str = Field(min_length=1, pattern=SLUG)

    @model_validator(mode="after")
    def script_checks(self):
        scene_coordinates(self.chapter, self.act, 1)
        for value in (*self.characters, *self.thread_keys):
            if not re.fullmatch(SLUG, value):
                raise ValueError("Character and plot thread IDs must be stable slugs")
        if len(set(self.characters)) != len(self.characters) or (
            len(set(self.thread_keys)) != len(self.thread_keys)
        ):
            raise ValueError("Duplicated scene references")
        plot_spans(self.text, [p.model_dump() for p in self.plot_points])
        return self


class ApproveSceneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: str = Field(default="main", pattern=SLUG)
    proof_digest: str = Field(pattern="^[a-f0-9]{64}$")
    expected_revision: int = Field(ge=1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(scope: dict, branch: str, kind: str, index: int) -> str:
    return sha256("|".join((
        scope["tenant_id"], scope["owner_id"], scope["game_id"],
        branch, kind, str(index),
    )).encode("utf-8")).hexdigest()


def _public(value: dict | None):
    return {k: v for k, v in value.items() if k not in (
        "_id", "tenant_id", "owner_id", "payload_digest",
    )} if value else None


async def _existing_game(pid: str, scope: dict) -> None:
    # The pipeline project has no native owner fields; project-specific story
    # notes and scenes are nevertheless strictly isolated by request identity.
    game = await _db.game_kb.find_one({"game_id": pid}, {"_id": 1})
    if not game:
        raise HTTPException(status_code=404, detail="Canonical game knowledge base not found")


async def _persist(collection, doc: dict, expected: int) -> tuple[dict, bool]:
    """CAS: stale clients cannot overwrite a concurrent chapter/scene edit."""
    old = await collection.find_one({"_id": doc["_id"]})
    if old and old.get("payload_digest") == doc["payload_digest"]:
        return old, True
    if old:
        if old.get("revision") != expected:
            raise HTTPException(status_code=409, detail="Document revision changed; reload before editing")
        updated = await collection.replace_one({"_id": doc["_id"], "revision": expected}, doc)
        if updated.matched_count != 1:
            raise HTTPException(status_code=409, detail="Document changed concurrently")
    else:
        if expected != 0:
            raise HTTPException(status_code=409, detail="No previous document with that revision")
        try:
            await collection.insert_one(doc)
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Document was concurrently created")
    return doc, False


async def _chapter(scope: dict, branch: str, chapter: int) -> dict:
    doc = await _db.game_story_chapters.find_one({
        "_id": _id(scope, branch, "chapter", chapter), **scope,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Chapter notes are missing")
    return doc


async def _scene(scope: dict, branch: str, scene: int) -> dict:
    doc = await _db.game_story_scenes.find_one({
        "_id": _id(scope, branch, "scene", scene), **scope,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Scene draft is missing")
    return doc


async def _global_style_guard(scope: dict, branch: str, incoming: dict,
                              chapter_no: int) -> None:
    rows = await _db.game_story_chapters.find(
        {**scope, "branch_id": branch},
        {"era_id": 1, "style_id": 1, "palette_id": 1, "voice_cast": 1, "chapter": 1},
    ).limit(MAX_CHAPTERS + 1).to_list(length=MAX_CHAPTERS + 1)
    if len(rows) > MAX_CHAPTERS:
        raise HTTPException(status_code=409, detail="Chapter index exceeds the authorized capacity")
    for prior in rows:
        if prior["chapter"] == chapter_no:
            continue
        for character, voice in incoming["voice_cast"].items():
            if character in prior.get("voice_cast", {}) and prior["voice_cast"][character] != voice:
                raise HTTPException(status_code=409, detail=(
                    "Character " + character + " voice identity cannot be silently replaced"
                ))
        if any(incoming[key] != prior[key] for key in ("era_id", "style_id", "palette_id")):
            if not incoming.get("transition_reason"):
                raise HTTPException(status_code=409, detail=(
                    "Era/style/palette drift requires an explicit documented transition"
                ))


@router.put("/{pid}/chapters/{chapter}")
async def save_chapter(
    pid: str, chapter: int, body: ChapterIn,
    user=Depends(require_role("editor")),
):
    scope = _scope(pid, user)
    if not 1 <= chapter <= MAX_CHAPTERS:
        raise HTTPException(status_code=422, detail="Chapter out of range")
    try:
        await _existing_game(pid, scope)
        incoming = body.model_dump(exclude={"expected_revision"})
        await _global_style_guard(scope, body.branch_id, incoming, chapter)
        existing_note = await _db.game_story_chapters.find_one({
            "_id": _id(scope, body.branch_id, "chapter", chapter),
        })
        if existing_note:
            for character, voice in existing_note.get("voice_cast", {}).items():
                if character in incoming["voice_cast"] and incoming["voice_cast"][character] != voice:
                    raise HTTPException(status_code=409, detail=(
                        "Existing character voice identity cannot be silently replaced"
                    ))
            if existing_note.get("payload_digest") != digest(incoming):
                approved = await _db.game_story_scenes.find_one({
                    **scope, "branch_id": body.branch_id, "chapter": chapter,
                    "status": "approved_for_production",
                })
                if approved:
                    raise HTTPException(status_code=409, detail=(
                        "Approved scenes lock their chapter notes. Fork a branch to revise."
                    ))
        revision = body.expected_revision + 1
        chapter_doc = {
            "_id": _id(scope, body.branch_id, "chapter", chapter),
            **scope, "chapter": chapter, **incoming, "revision": revision,
            "updated_at": _now(),
        }
        chapter_doc["payload_digest"] = digest(incoming)
        chapter_doc["digest"] = digest({**incoming, "chapter": chapter, "revision": revision})
        saved, replay = await _persist(
            _db.game_story_chapters, chapter_doc, body.expected_revision,
        )
        return {"ok": True, "chapter": _public(saved), "receipt": saved["digest"],
                "replayed": replay}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        logger.exception("chapter context persistence unavailable")
        raise HTTPException(status_code=503, detail="Chapter storage unavailable")


@router.get("/{pid}/chapters")
async def list_chapters(
    pid: str, branch_id: str = Query("main", pattern=SLUG),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    try:
        docs = await _db.game_story_chapters.find(
            {**scope, "branch_id": branch_id},
            {"_id": 0, "owner_id": 0, "tenant_id": 0, "payload_digest": 0},
        ).sort("chapter", 1).limit(MAX_CHAPTERS + 1).to_list(length=MAX_CHAPTERS + 1)
        if len(docs) > MAX_CHAPTERS:
            raise HTTPException(status_code=409, detail="Chapter index capacity exceeded")
        return {"ok": True, "game_id": pid, "branch_id": branch_id,
                "chapters": [_public(x) for x in docs],
                "count": len(docs), "max_chapters": MAX_CHAPTERS}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Chapter storage unavailable")


@router.get("/{pid}/chapters/{chapter}/context")
async def get_chapter_context(
    pid: str, chapter: int, branch_id: str = Query("main", pattern=SLUG),
    max_chars: int = Query(6000, ge=256, le=12000),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    if not 1 <= chapter <= MAX_CHAPTERS:
        raise HTTPException(status_code=422, detail="Chapter out of range")
    try:
        info = await _chapter(scope, branch_id, chapter)
        docs = await _db.game_story_scenes.find(
            {**scope, "branch_id": branch_id, "chapter": chapter},
        ).sort("scene", -1).limit(MAX_SCENES + 1).to_list(length=MAX_SCENES + 1)
        complete = len(docs) <= MAX_SCENES
        projection = chapter_context(info, docs[:MAX_SCENES],
                                     max_chars=max_chars, complete=complete)
        return {"ok": True, "game_id": pid, "branch_id": branch_id,
                "chapter": _public(info), "context": projection}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Chapter context unavailable")


@router.put("/{pid}/scenes/{scene}")
async def save_scene(
    pid: str, scene: int, body: SceneIn,
    user=Depends(require_role("editor")),
):
    scope = _scope(pid, user)
    try:
        scene_coordinates(body.chapter, body.act, scene)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    try:
        await _existing_game(pid, scope)
        ch = await _chapter(scope, body.branch_id, body.chapter)
        if body.chapter_revision != ch["revision"] or body.chapter_digest != ch["digest"]:
            raise HTTPException(status_code=409, detail="Chapter notes have changed; refresh scene context")
        for actor in body.characters:
            if actor not in ch["voice_cast"]:
                raise HTTPException(status_code=409, detail=(
                    "No stable voice identity is recorded for character " + actor
                ))
        incoming = body.model_dump(exclude={"expected_revision"})
        existing_scene = await _db.game_story_scenes.find_one({
            "_id": _id(scope, body.branch_id, "scene", scene),
        })
        if existing_scene and existing_scene.get("status") == "approved_for_production":
            if existing_scene.get("payload_digest") != digest(incoming):
                raise HTTPException(status_code=409, detail=(
                    "Approved scenes are immutable. Fork a story branch to revise canon."
                ))
        revision = body.expected_revision + 1
        record = {
            "_id": _id(scope, body.branch_id, "scene", scene),
            **scope, **incoming, "scene": scene, "revision": revision,
            "status": "draft", "proof": None, "approved_at": None,
            "updated_at": _now(),
        }
        record["payload_digest"] = digest(incoming)
        record["digest"] = digest({"scene": scene, "revision": revision, **incoming})
        saved, replay = await _persist(
            _db.game_story_scenes, record, body.expected_revision,
        )
        return {"ok": True, "scene": _public(saved), "receipt": saved["digest"],
                "replayed": replay}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        logger.exception("story scene persistence unavailable")
        raise HTTPException(status_code=503, detail="Scene storage unavailable")


@router.get("/{pid}/scenes")
async def list_scenes(
    pid: str,
    branch_id: str = Query("main", pattern=SLUG),
    chapter: int = Query(..., ge=1, le=MAX_CHAPTERS),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=MAX_SCENES),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    try:
        records = await _db.game_story_scenes.find(
            {**scope, "branch_id": branch_id, "chapter": chapter},
        ).sort("scene", 1).skip(offset).limit(limit + 1).to_list(length=limit + 1)
        # Omit full scripts from index pages, but keep plot highlights/receipts.
        items = [{
            k: v for k, v in _public(x).items()
            if k not in ("text", "proof")
        } for x in records[:limit]]
        return {
            "ok": True, "game_id": pid, "branch_id": branch_id,
            "chapter": chapter, "scenes": items,
            "next_offset": offset + limit if len(records) > limit else None,
        }
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Scene listing unavailable")


@router.get("/{pid}/scenes/{scene}")
async def get_scene(
    pid: str, scene: int,
    branch_id: str = Query("main", pattern=SLUG),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    if not 1 <= scene <= MAX_SCENES:
        raise HTTPException(status_code=422, detail="Scene out of range")
    try:
        record = await _scene(scope, branch_id, scene)
        return {"ok": True, "scene": _public(record),
                "highlights": plot_spans(record["text"], record["plot_points"])}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Scene read unavailable")


async def _audit_previous(scope: dict, branch: str, scene: int):
    """Only prior story events; foreign later scenes must not seed knowledge."""
    cursor = _db.game_story_events.find({
        **scope, "branch_id": branch, "scene": {"$lt": scene},
    }).sort([("act", 1), ("scene", 1), ("beat", 1), ("event_id", 1)])
    audit = StoryAuditAccumulator(bookmark_limit=30)
    complete = True
    async for event in cursor:
        if audit.event_count >= MAX_STREAM_EVENTS:
            complete = False
            break
        audit.ingest(event)
    return audit.finish(complete=complete)


@router.post("/{pid}/scenes/{scene}/proofread")
async def proofread_scene(
    pid: str, scene: int,
    branch_id: str = Query("main", pattern=SLUG),
    user=Depends(require_role("editor")),
):
    scope = _scope(pid, user)
    try:
        record = await _scene(scope, branch_id, scene)
        ch = await _chapter(scope, branch_id, record["chapter"])
        history = await _audit_previous(scope, branch_id, scene)
        predecessor = None
        if scene > 1:
            predecessor = await _db.game_story_scenes.find_one({
                "_id": _id(scope, branch_id, "scene", scene - 1), **scope,
            })
        proof = proofreading_checks(
            record, ch,
            history_complete=history["complete"],
            history_issues=history["issues"],
            predecessor=predecessor,
        )
        # A proof is for the exact script revision. Concurrent edits must not
        # make the proof look current; CAS binds the resulting stored receipt.
        updated = await _db.game_story_scenes.update_one(
            {"_id": record["_id"], "revision": record["revision"],
             "digest": record["digest"], "status": "draft"},
            {"$set": {"proof": proof, "proofed_at": _now()}},
        )
        if updated.matched_count != 1:
            raise HTTPException(status_code=409, detail="Scene changed while proofreading")
        return {"ok": True, "proof": proof, "scene_receipt": record["digest"]}
    except HTTPException:
        raise
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=409, detail="Story evidence invalid: " + str(exc))
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Story proofreading storage unavailable")


@router.post("/{pid}/scenes/{scene}/approve")
async def approve_scene(
    pid: str, scene: int, body: ApproveSceneIn,
    user=Depends(require_role("editor")),
):
    scope = _scope(pid, user)
    try:
        record = await _scene(scope, body.branch_id, scene)
        ch = await _chapter(scope, body.branch_id, record["chapter"])
        proof = record.get("proof") or {}
        predecessor = None
        if scene > 1:
            predecessor = await _db.game_story_scenes.find_one({
                "_id": _id(scope, body.branch_id, "scene", scene - 1), **scope,
            })
        expected_previous_receipt = predecessor.get("digest") if predecessor else None
        previous_approved = (scene == 1 or (
            predecessor is not None and
            predecessor.get("status") == "approved_for_production" and
            predecessor.get("act", 0) <= record["act"]
        ))
        if record["status"] == "approved_for_production" and (
            proof.get("receipt_digest") == body.proof_digest
        ):
            return {"ok": True, "replayed": True, "status": record["status"],
                    "scene_receipt": record["digest"], "proof_digest": body.proof_digest}
        if (record["status"] != "draft" or record["revision"] != body.expected_revision
            or record["chapter_revision"] != ch["revision"]
            or record["chapter_digest"] != ch["digest"]
            or proof.get("receipt_digest") != body.proof_digest
            or proof.get("scene_digest") != record["digest"]
            or proof.get("status") != "machine_checks_passed"
            or proof.get("inspections_executed") != 100000
            or proof.get("history_complete") is not True
            or not previous_approved
            or proof.get("predecessor_scene_digest") != expected_previous_receipt
            or proof.get("blocking_issues")
        ):
            raise HTTPException(status_code=409, detail=(
                "Proof expired, incomplete or blocked. Re-run scene review before approval."
            ))
        changed = await _db.game_story_scenes.update_one(
            {"_id": record["_id"], "revision": record["revision"],
             "digest": record["digest"], "status": "draft",
             "proof.receipt_digest": body.proof_digest},
            {"$set": {"status": "approved_for_production",
                      "approved_at": _now(), "approved_by": scope["owner_id"]}},
        )
        if changed.matched_count != 1:
            raise HTTPException(status_code=409, detail="Scene approval changed concurrently")
        return {"ok": True, "replayed": False, "status": "approved_for_production",
                "scene_receipt": record["digest"], "proof_digest": body.proof_digest,
                "production_note": "Narrative approval only: no rendered assets or compiled game are implied"}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Story production approval unavailable")
