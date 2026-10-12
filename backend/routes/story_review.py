"""Authenticated 100x100 scene review receipts; editor-approved, not model fiat.

Jeeves generates *candidate* critiques via canonical chat. Its output cannot
silently mark a review as passed. A human editor may adopt an independently
supported finding with exact scene quote, matrix ID and level. Every cell is
immutable and bound to the current scene revision. Truncated or missing cells
never count toward completion.
"""
from __future__ import annotations

from hashlib import sha256
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.story_review_matrices import (
    REQUIRED_CELLS, REVIEW_MATRIX_COUNT, MATRIX_IDS, coverage,
    matrix_catalog, review_cell, review_prompt,
)
from routes.gameforge_auth import require_role
from routes.story_index import _scope
from routes.playable import _db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Jeeves narrative quality review"])


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    branch_id: str = Field(default="main", pattern=r"^[A-Za-z0-9:_-]{1,96}$")
    scene_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    matrix_id: str = Field(min_length=5, max_length=100)
    level: int = Field(ge=1, le=100)
    verdict: str
    rationale: str = Field(min_length=12, max_length=1200)
    citation_quote: str = Field(min_length=2, max_length=500)
    citation_plot_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9:_-]{1,96}$")
    provenance: str = Field(default="jeeves_model_candidate")
    reviewed_and_approved_by_creator: bool = False


class AdoptCandidateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: str = Field(default="main", pattern=r"^[A-Za-z0-9:_-]{1,96}$")
    scene_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    matrix_id: str = Field(min_length=5, max_length=100)
    level: int = Field(ge=1, le=100)
    candidate_receipt: str = Field(pattern=r"^[a-f0-9]{64}$")


def _review_id(scope: dict, branch: str, scene: int, digest: str,
               matrix: str, level: int) -> str:
    return sha256("|".join((scope["tenant_id"], scope["owner_id"],
        scope["game_id"], branch, str(scene), digest, matrix, str(level))).encode()).hexdigest()


async def _authoritative_scene(scope: dict, branch: str, scene: int) -> dict:
    if not 1 <= scene <= 9999:
        raise HTTPException(status_code=422, detail="Scene out of range")
    from routes.chapter_studio import _id
    row = await _db.game_story_scenes.find_one({
        "_id": _id(scope, branch, "scene", scene), **scope,
    })
    if not row:
        raise HTTPException(status_code=404, detail="Saved scene not found")
    return row


@router.get("/{pid}/story-matrices")
async def list_story_matrices(
    pid: str, start: int = Query(0, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(require_role("viewer")),
):
    _scope(pid, user)
    return {"ok": True, "game_id": pid, "catalog": matrix_catalog(start=start, limit=limit)}


@router.get("/{pid}/scenes/{scene}/matrix-prompt")
async def get_matrix_prompt(
    pid: str, scene: int, branch_id: str = Query("main", pattern=r"^[A-Za-z0-9:_-]{1,96}$"),
    matrix_id: str = Query(...), level: int = Query(..., ge=1, le=100),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    try:
        draft = await _authoritative_scene(scope, branch_id, scene)
        return {"ok": True, "game_id": pid, "branch_id": branch_id,
            "scene_receipt": draft["digest"],
            "prompt": review_prompt(matrix_id, level,
                                    chapter=draft["chapter"], scene=scene)}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Matrix review source unavailable")


@router.post("/{pid}/scenes/{scene}/matrix-review")
async def submit_matrix_review(
    pid: str, scene: int, body: ReviewSubmission,
    user=Depends(require_role("editor")),
):
    scope = _scope(pid, user)
    try:
        draft = await _authoritative_scene(scope, body.branch_id, scene)
        if body.scene_digest != draft["digest"]:
            raise HTTPException(status_code=409, detail="Scene changed; review the new revision")
        if body.provenance == "jeeves_model_candidate" and body.reviewed_and_approved_by_creator:
            raise HTTPException(status_code=409, detail=(
                "An unexamined model candidate cannot self-certify its review"
            ))
        quote = body.citation_quote
        # Exact-highlight anchoring is required whenever the reviewer cites
        # a named plot point, not merely a substring in a long script.
        if body.citation_plot_id and not any(
            p.get("id") == body.citation_plot_id and quote in p.get("anchor", "")
            for p in draft.get("plot_points", [])
        ):
            raise HTTPException(status_code=422, detail="Plot citation did not match an anchored passage")
        entry = review_cell(
            matrix_id=body.matrix_id, level=body.level, verdict=body.verdict,
            rationale=body.rationale, citation_scene=scene,
            citation_plot_id=body.citation_plot_id, citation_quote=quote,
            source_receipt=draft["digest"],
            reviewer="reviewer_" + sha256(scope["owner_id"].encode("utf-8")).hexdigest()[:24],
            provenance=body.provenance,
            scene_text=draft["text"], scene_digest=draft["digest"],
        )
        entry["creator_approved"] = bool(body.reviewed_and_approved_by_creator and
                                         body.provenance != "jeeves_model_candidate")
        identity = _review_id(scope, body.branch_id, scene, draft["digest"],
                              body.matrix_id, body.level)
        stored = {**scope, **entry, "_id": identity, "branch_id": body.branch_id,
                  "scene": scene, "source_message_id": draft["source_message_id"]}
        try:
            await _db.game_story_reviews.insert_one(stored)
            replay = False
        except DuplicateKeyError:
            previous = await _db.game_story_reviews.find_one({"_id": identity, **scope})
            if not previous or previous.get("review_digest") != entry["review_digest"] or (
                previous.get("creator_approved") != stored["creator_approved"]
            ):
                raise HTTPException(status_code=409, detail=(
                    "This review cell already has a different finding. Do not overwrite evidence."
                ))
            replay = True
        return {"ok": True, "replayed": replay,
                "review_receipt": entry["review_digest"],
                "matrix_id": body.matrix_id, "level": body.level,
                "creator_approved": entry["creator_approved"],
                "model_quality_guaranteed": False}
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except (PyMongoError, OSError):
        logger.exception("Matrix audit evidence persistence failed")
        raise HTTPException(status_code=503, detail="Matrix review storage unavailable")


@router.get("/{pid}/scenes/{scene}/matrix-coverage")
async def get_matrix_coverage(
    pid: str, scene: int,
    branch_id: str = Query("main", pattern=r"^[A-Za-z0-9:_-]{1,96}$"),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    try:
        draft = await _authoritative_scene(scope, branch_id, scene)
        reviews = await _db.game_story_reviews.find({
            **scope, "branch_id": branch_id, "scene": scene,
            "scene_digest": draft["digest"],
        }).limit(REQUIRED_CELLS + 1).to_list(length=REQUIRED_CELLS + 1)
        if len(reviews) > REQUIRED_CELLS:
            raise HTTPException(status_code=409, detail="Review matrix index exceeds capacity")
        result = coverage(reviews, scene_digest=draft["digest"])
        return {"ok": True, "scene": scene, "branch_id": branch_id,
                "scene_receipt": draft["digest"], "coverage": result}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        logger.exception("Matrix audit coverage unavailable")
        raise HTTPException(status_code=503, detail="Matrix coverage unavailable")



@router.post("/{pid}/scenes/{scene}/matrix-finalize")
async def finalize_scene_matrices(
    pid: str, scene: int,
    branch_id: str = Query("main", pattern=r"^[A-Za-z0-9:_-]{1,96}$"),
    user=Depends(require_role("editor")),
):
    """Compute one compact, replay-safe receipt for 10,000 independent cells.

    Production inventory may read this summary, instead of scanning up to
    100 million individual review documents for the entire 9,999-scene game.
    A human-reviewed PASS in every cell is required; model candidates,
    failures, missing cells, duplicate indexes and stale scripts fail closed.
    """
    scope = _scope(pid, user)
    try:
        draft = await _authoritative_scene(scope, branch_id, scene)
        rows = await _db.game_story_reviews.find({
            **scope, "branch_id": branch_id, "scene": scene,
            "scene_digest": draft["digest"],
        }).limit(REQUIRED_CELLS + 1).to_list(length=REQUIRED_CELLS + 1)
        if len(rows) > REQUIRED_CELLS:
            raise HTTPException(status_code=409, detail="Matrix cell count exceeds capacity")
        result = coverage(rows, scene_digest=draft["digest"])
        if not result["fully_reviewed"]:
            raise HTTPException(status_code=409, detail={
                "reason": "Matrix review incomplete or contradicted",
                "coverage": result,
            })
        canonical_rows = sorted(
            (x["matrix_id"], x["level"], x["review_digest"]) for x in rows
        )
        review_receipt = sha256(json.dumps(
            {"scene_digest": draft["digest"], "rows": canonical_rows},
            separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        current = (draft.get("matrix_review") or {}).get("receipt_digest")
        if current == review_receipt:
            return {"ok": True, "replayed": True,
                    "scene_receipt": draft["digest"],
                    "matrix_review_receipt": review_receipt, "coverage": result}
        updated = await _db.game_story_scenes.update_one({
            "_id": draft["_id"], **scope, "revision": draft["revision"],
            "digest": draft["digest"],
        }, {"$set": {"matrix_review": {
            "receipt_digest": review_receipt,
            "scene_digest": draft["digest"],
            "cells_approved": REQUIRED_CELLS,
            "model_output_independently_guaranteed": False,
        }}})
        if updated.matched_count != 1:
            raise HTTPException(status_code=409, detail="Scene changed during matrix finalization")
        return {"ok": True, "replayed": False,
                "scene_receipt": draft["digest"],
                "matrix_review_receipt": review_receipt, "coverage": result}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        logger.exception("Final matrix coverage could not be saved")
        raise HTTPException(status_code=503, detail="Matrix review persistence unavailable")



@router.post("/{pid}/scenes/{scene}/matrix-review/approve-candidate")
async def approve_model_candidate(
    pid: str, scene: int, body: AdoptCandidateIn,
    user=Depends(require_role("editor")),
):
    """Human acceptance of an immutable Jeeves candidate, without rewriting it."""
    scope = _scope(pid, user)
    try:
        draft = await _authoritative_scene(scope, body.branch_id, scene)
        if draft["digest"] != body.scene_digest:
            raise HTTPException(status_code=409, detail="Scene changed since model review")
        if body.matrix_id not in MATRIX_IDS:
            raise HTTPException(status_code=422, detail="Unknown story matrix")
        rid = _review_id(scope, body.branch_id, scene, body.scene_digest,
                         body.matrix_id, body.level)
        candidate = await _db.game_story_reviews.find_one({"_id": rid, **scope})
        if not candidate or candidate.get("review_digest") != body.candidate_receipt:
            raise HTTPException(status_code=404, detail="Matching model critique not found")
        if candidate.get("provenance") != "jeeves_model_candidate":
            raise HTTPException(status_code=409, detail="Only model candidates use this approval route")
        if candidate.get("creator_approved") is True:
            return {"ok": True, "replayed": True, "review_receipt": body.candidate_receipt,
                    "verdict": candidate["verdict"], "creator_approved": True}
        updated = await _db.game_story_reviews.update_one(
            {"_id": rid, **scope, "review_digest": body.candidate_receipt,
             "creator_approved": False, "provenance": "jeeves_model_candidate"},
            {"$set": {"creator_approved": True,
                      "approved_by": sha256(scope["owner_id"].encode()).hexdigest()[:24]}},
        )
        if updated.matched_count != 1:
            raise HTTPException(status_code=409, detail="Candidate changed during review")
        return {"ok": True, "replayed": False,
                "review_receipt": body.candidate_receipt,
                "verdict": candidate["verdict"], "creator_approved": True}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Model-review approval storage unavailable")
