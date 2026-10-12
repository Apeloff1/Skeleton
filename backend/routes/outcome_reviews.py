"""Evidence-backed 1000×100 ending review records; bounded and fail-closed.

One immutable cell per (tenant, owner, game, branch, plan digest, ending, matrix,
level). Every conclusion cites a real authored dialogue/scene or ending passage.
An unreviewed model candidate never counts as approved. A historical edit
changes the plan digest and invalidates all prior quality signoffs.
"""
from __future__ import annotations

from hashlib import sha256
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.outcome_weaving_matrices import catalog, coverage_summary, matrix, instruction
from core.branching_narrative import simulate
from routes.story_index import _scope
from routes.gameforge_auth import require_role
from routes.playable import _db

router = APIRouter(tags=["Jeeves multi-ending proofreader"])
logger = logging.getLogger(__name__)
SLUG = r"^[A-Za-z0-9:_-]{1,96}$"
HASH = r"^[a-f0-9]{64}$"


class EndingReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    branch_id: str = Field(default="main", pattern=SLUG)
    plan_digest: str = Field(pattern=HASH)
    ending_id: str = Field(pattern=SLUG)
    matrix_id: str = Field(min_length=5, max_length=140)
    level: int = Field(ge=1, le=100)
    verdict: str
    rationale: str = Field(min_length=12, max_length=1400)
    quote: str = Field(min_length=2, max_length=500)
    source_node_id: str | None = Field(default=None, pattern=SLUG)
    witness_choices: list[str] = Field(default_factory=list, max_length=2000)
    provenance: str = "creator"
    creator_approved: bool = False


class EndorseEndingReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: str = Field(default="main", pattern=SLUG)
    plan_digest: str = Field(pattern=HASH)
    ending_id: str = Field(pattern=SLUG)
    matrix_id: str = Field(min_length=5, max_length=140)
    level: int = Field(ge=1, le=100)
    review_receipt: str = Field(pattern=HASH)


def _identity(scope: dict, branch: str, digest: str, ending: str,
              matrix_id: str, level: int) -> str:
    return sha256("|".join((scope["tenant_id"], scope["owner_id"], scope["game_id"],
        branch, digest, ending, matrix_id, str(level))).encode("utf-8")).hexdigest()


async def _plan(scope: dict, branch: str):
    from routes.story_outcomes import _find
    return await _find(scope, branch)


def _review_payload(body: EndingReviewIn, plan: dict, scope: dict) -> dict:
    compiled = plan["compiled"]
    if body.plan_digest != compiled["source_digest"]:
        raise HTTPException(status_code=409, detail="Ending matrix refers to an obsolete plan revision")
    if body.ending_id not in compiled["endings"]:
        raise HTTPException(status_code=404, detail="Referenced ending does not exist")
    try:
        matrix(body.matrix_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if body.verdict not in ("pass", "fail", "unknown"):
        raise HTTPException(status_code=422, detail="Review verdict must be pass, fail or unknown")
    if body.provenance not in ("creator", "jeeves_model_candidate", "external_reviewer"):
        raise HTTPException(status_code=422, detail="Unknown review provenance")
    if body.provenance == "jeeves_model_candidate" and body.creator_approved:
        raise HTTPException(status_code=409, detail="Model output cannot certify itself")
    if any(not isinstance(x, str) or not x or len(x) > 96
           for x in body.witness_choices):
        raise HTTPException(status_code=422, detail="Invalid player-choice witness")
    if body.source_node_id:
        node = compiled["nodes"].get(body.source_node_id)
        if not node:
            raise HTTPException(status_code=422, detail="Evidence node does not exist")
        # The witness must be an actual enabled path that reaches this exact
        # ending and includes the node referenced by the review.
        try:
            play = simulate(compiled, body.witness_choices)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Invalid reachable playthrough witness: " + str(exc))
        if play["ending_id"] != body.ending_id or not any(
            step["node"] == body.source_node_id for step in play["steps"]
        ):
            raise HTTPException(status_code=422, detail="Evidence node is not on a witnessed ending path")
        accepted_quotes = [node["text"]] + [
            opt["dialogue"] for opt in node["options"]
            if opt["id"] in set(body.witness_choices)
        ]
        if not any(body.quote in s for s in accepted_quotes):
            raise HTTPException(status_code=422, detail="Quoted evidence not present in visited dialogue")
        witness_receipt = play["receipt_digest"]
    else:
        witnessed_ending = None
        if body.witness_choices:
            try:
                play = simulate(compiled, body.witness_choices)
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=422, detail="Invalid ending witness: " + str(exc))
            if play["ending_id"] != body.ending_id:
                raise HTTPException(status_code=422, detail="Player history reaches a different ending")
            witness_receipt = play["receipt_digest"]
            witnessed_ending = play["ending"]
        else:
            witness_receipt = None
        ending = witnessed_ending or compiled["endings"][body.ending_id]
        endings_text = [ending["epilogue"], ending["consequences"]]
        for field in ("character_conclusions", "place_conclusions",
                      "quest_conclusions", "faction_conclusions"):
            endings_text.extend(ending[field].values())
        if not any(body.quote in s for s in endings_text):
            raise HTTPException(status_code=422, detail="Ending quote absent from authored consequence")
    row = {
        "matrix_id": body.matrix_id, "level": body.level, "verdict": body.verdict,
        "rationale": body.rationale, "quote": body.quote,
        "source_node_id": body.source_node_id,
        "ending_id": body.ending_id, "plan_digest": body.plan_digest,
        "branch_id": body.branch_id, "witness_receipt": witness_receipt,
        "provenance": body.provenance,
        "creator_approved": bool(body.creator_approved and
                                 body.provenance != "jeeves_model_candidate"),
    }
    row["review_digest"] = sha256(json.dumps(row, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return row


@router.post("/{pid}/outcomes/matrix-review")
async def submit_outcome_review(pid: str, body: EndingReviewIn,
                                user=Depends(require_role("editor"))):
    scope = _scope(pid, user)
    try:
        stored_plan = await _plan(scope, body.branch_id)
        record = _review_payload(body, stored_plan, scope)
        uid = _identity(scope, body.branch_id, body.plan_digest,
                        body.ending_id, body.matrix_id, body.level)
        row = {"_id": uid, **scope, **record}
        try:
            await _db.game_story_outcome_reviews.insert_one(row)
            replayed = False
        except DuplicateKeyError:
            prior = await _db.game_story_outcome_reviews.find_one({
                "_id": uid, **scope,
            })
            if not prior or prior["review_digest"] != record["review_digest"]:
                raise HTTPException(status_code=409, detail="Matrix finding already recorded with different evidence")
            replayed = True
        return {"ok": True, "replayed": replayed,
                "review_receipt": record["review_digest"],
                "creator_approved": prior["creator_approved"] if replayed else record["creator_approved"],
                "plan_digest": body.plan_digest, "ending_id": body.ending_id}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        logger.exception("Ending evidence write failed")
        raise HTTPException(status_code=503, detail="Ending review persistence unavailable")


@router.post("/{pid}/outcomes/matrix-review/approve-candidate")
async def approve_outcome_review(pid: str, body: EndorseEndingReview,
                                 user=Depends(require_role("editor"))):
    scope = _scope(pid, user)
    try:
        stored_plan = await _plan(scope, body.branch_id)
        if stored_plan["source_digest"] != body.plan_digest:
            raise HTTPException(status_code=409, detail="Story plan has changed")
        uid = _identity(scope, body.branch_id, body.plan_digest,
                        body.ending_id, body.matrix_id, body.level)
        prior = await _db.game_story_outcome_reviews.find_one({
            "_id": uid, **scope,
        })
        if not prior or prior.get("review_digest") != body.review_receipt:
            raise HTTPException(status_code=404, detail="Exact review candidate not found")
        if prior["creator_approved"]:
            return {"ok": True, "replayed": True,
                    "review_receipt": body.review_receipt, "creator_approved": True}
        if prior["provenance"] != "jeeves_model_candidate":
            raise HTTPException(status_code=409, detail="This candidate requires explicit creator review")
        updated = await _db.game_story_outcome_reviews.update_one({
            "_id": uid, **scope, "creator_approved": False,
            "review_digest": body.review_receipt,
        }, {"$set": {"creator_approved": True,
                     "approved_by": sha256(scope["owner_id"].encode()).hexdigest()[:24]}})
        if updated.matched_count != 1:
            raise HTTPException(status_code=409, detail="Review changed concurrently")
        return {"ok": True, "replayed": False,
                "review_receipt": body.review_receipt, "creator_approved": True}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Ending review approval unavailable")


@router.get("/{pid}/outcomes/matrix-coverage")
async def outcome_matrix_coverage(
    pid: str,
    branch_id: str = Query("main", pattern=SLUG),
    ending_id: str = Query(..., pattern=SLUG),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    try:
        stored_plan = await _plan(scope, branch_id)
        if ending_id not in stored_plan["compiled"]["endings"]:
            raise HTTPException(status_code=404, detail="Unknown ending")
        rows = await _db.game_story_outcome_reviews.find({
            **scope, "branch_id": branch_id, "plan_digest": stored_plan["source_digest"],
            "ending_id": ending_id,
        }).limit(100001).to_list(length=100001)
        if len(rows) > 100000:
            raise HTTPException(status_code=409, detail="Narrative matrix ledger exceeds 100000 cells")
        result = coverage_summary(rows, plan_digest=stored_plan["source_digest"],
                                  ending_id=ending_id)
        return {"ok": True, "game_id": pid, "branch_id": branch_id,
                "plan_digest": stored_plan["source_digest"], "ending_id": ending_id,
                "coverage": result}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        logger.exception("Ending coverage read unavailable")
        raise HTTPException(status_code=503, detail="Ending matrix coverage unavailable")
