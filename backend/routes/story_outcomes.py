"""Jeeves branching outcome studio: immutable revisions and pure simulations.

Full narrative plan stores in one scoped project document; large source works
can later be decomposed into chunks. This route does not execute game actions.
Choices are replayed as a deterministic authoring/QA simulation and the exact
history/ending/guard receipts are returned. Publication to a playable game
remains a separately validated assembly operation.
"""
from __future__ import annotations
from hashlib import sha256
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.branching_narrative import validate_plan, simulate, audit_outcomes
from core.outcome_weaving_matrices import catalog, instruction
from routes.story_index import _scope
from routes.chapter_studio import _existing_game
from routes.gameforge_auth import require_role
from routes.playable import _db

router = APIRouter(tags=["Jeeves branching game narrative"])
logger = logging.getLogger(__name__)
ID = r"^[A-Za-z0-9:_-]{1,96}$"


class SavePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0, le=1000000)
    branch_id: str = Field(default="main", pattern=ID)
    plan: dict


class SimulateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: str = Field(default="main", pattern=ID)
    choices: list[str] = Field(default_factory=list, max_length=2000)


def _key(scope: dict, branch: str) -> str:
    raw = "|".join((scope["tenant_id"], scope["owner_id"],
                    scope["game_id"], branch, "branching-plan-v1"))
    return sha256(raw.encode()).hexdigest()


def _public(doc: dict):
    return {k: v for k, v in doc.items()
            if k not in {"_id", "tenant_id", "owner_id"}} if doc else None


async def _find(scope: dict, branch: str) -> dict:
    row = await _db.game_story_outcome_plans.find_one({
        "_id": _key(scope, branch), **scope,
    })
    if not row:
        raise HTTPException(status_code=404, detail="No authored branching narrative for this timeline")
    return row


@router.put("/{pid}/outcomes/plan")
async def save_outcome_plan(pid: str, body: SavePlan,
                            user=Depends(require_role("editor"))):
    scope = _scope(pid, user)
    if body.plan.get("branch_id") != body.branch_id:
        raise HTTPException(status_code=422, detail="Plan and route branches differ")
    # Bound the whole payload far below Mongo's 16 MB document ceiling.
    if len(json.dumps(body.plan, ensure_ascii=False)) > 1_200_000:
        raise HTTPException(status_code=413, detail="Branch plan exceeds 1.2 MB")
    try:
        compiled = validate_plan(body.plan)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    try:
        await _existing_game(pid, scope)
        key = _key(scope, body.branch_id)
        existing = await _db.game_story_outcome_plans.find_one({"_id": key, **scope})
        if existing and existing["source_digest"] == compiled["source_digest"]:
            return {"ok": True, "replayed": True, "revision": existing["revision"],
                    "plan_digest": existing["source_digest"],
                    "branch_id": body.branch_id}
        if (existing and existing["revision"] != body.expected_revision) or (
            not existing and body.expected_revision != 0
        ):
            raise HTTPException(status_code=409, detail="Narrative graph revision changed")
        new_version = body.expected_revision + 1
        record = {"_id": key, **scope, "branch_id": body.branch_id,
                  "revision": new_version, "source_digest": compiled["source_digest"],
                  "plan": body.plan, "compiled": compiled}
        if existing:
            result = await _db.game_story_outcome_plans.replace_one(
                {"_id": key, **scope, "revision": body.expected_revision},
                record,
            )
            if result.matched_count != 1:
                raise HTTPException(status_code=409, detail="Narrative graph was edited concurrently")
        else:
            try:
                await _db.game_story_outcome_plans.insert_one(record)
            except DuplicateKeyError:
                raise HTTPException(status_code=409, detail="Narrative graph created concurrently")
        return {"ok": True, "replayed": False, "revision": new_version,
                "plan_digest": compiled["source_digest"], "branch_id": body.branch_id}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        logger.exception("Branch narrative save unavailable")
        raise HTTPException(status_code=503, detail="Branch narrative storage unavailable")


@router.get("/{pid}/outcomes/plan")
async def get_outcome_plan(pid: str, branch_id: str = Query("main", pattern=ID),
                           user=Depends(require_role("viewer"))):
    scope = _scope(pid, user)
    try:
        record = await _find(scope, branch_id)
        return {"ok": True, "game_id": pid, "branch_id": branch_id,
                "revision": record["revision"], "plan_digest": record["source_digest"],
                "plan": record["plan"]}
    except HTTPException:
        raise
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Branch narrative read unavailable")


@router.post("/{pid}/outcomes/simulate")
async def simulate_outcomes(pid: str, body: SimulateIn,
                            user=Depends(require_role("viewer"))):
    scope = _scope(pid, user)
    try:
        record = await _find(scope, body.branch_id)
        result = simulate(record["compiled"], body.choices)
        return {"ok": True, "game_id": pid, "branch_id": body.branch_id,
                "revision": record["revision"], "simulation": result,
                "simulated_not_applied_to_game": True}
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Branch simulation unavailable")


@router.get("/{pid}/outcomes/audit")
async def audit_branch_outcomes(
    pid: str, branch_id: str = Query("main", pattern=ID),
    path_budget: int = Query(2000, ge=1, le=10000),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    try:
        record = await _find(scope, branch_id)
        result = audit_outcomes(record["compiled"], max_paths=path_budget)
        return {"ok": True, "game_id": pid, "branch_id": branch_id,
                "plan_digest": record["source_digest"], "audit": result}
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Branch outcome audit unavailable")


@router.get("/{pid}/outcomes/matrices")
async def list_outcome_matrices(
    pid: str, start: int = Query(0, ge=0, le=1000),
    limit: int = Query(50, ge=1, le=100),
    user=Depends(require_role("viewer")),
):
    _scope(pid, user)
    return {"ok": True, "game_id": pid,
            "catalog": catalog(start=start, limit=limit)}


@router.get("/{pid}/outcomes/matrix-prompt")
async def get_outcome_matrix_instruction(
    pid: str, branch_id: str = Query("main", pattern=ID),
    matrix_id: str = Query(..., min_length=5, max_length=140),
    level: int = Query(..., ge=1, le=100),
    ending_id: str = Query(..., pattern=ID),
    user=Depends(require_role("viewer")),
):
    scope = _scope(pid, user)
    try:
        record = await _find(scope, branch_id)
        if ending_id not in record["compiled"]["endings"]:
            raise HTTPException(status_code=404, detail="Target ending is not part of this plan")
        row = instruction(matrix_id, level, ending_id=ending_id,
                          player_history_digest=record["source_digest"])
        return {"ok": True, "game_id": pid, "branch_id": branch_id,
                "plan_digest": record["source_digest"], "instruction": row}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except (PyMongoError, OSError):
        raise HTTPException(status_code=503, detail="Outcome review instruction unavailable")
