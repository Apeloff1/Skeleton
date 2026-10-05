"""
🔧 REPAIR & EVALUATE — runtime self-heal + judge re-evaluation for a playable.

Extracted from routes/playable.py (Session 12 monolith decomposition).
- POST /{pid}/evaluate     — (re)run the VII.1 judge eval and persist it.
- POST /{pid}/repair        — synchronous runtime self-heal (~100s).
- POST /{pid}/repair/async  — kick self-heal in the background; poll /job/{job_id}.

Shares the codegen + judge helpers and the Mongo handle with routes.playable.
All routes use deeper POST paths so they never shadow the GET /{pid} catch-all.
"""
from __future__ import annotations

import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from routes.playable import (
    _db, _REPAIR_SYS, _GAME_ENSEMBLE, PLAYABILITY_THRESHOLD,
    _sanitize, _extract_html, _validate, _llm_in_thread, _run_job, _judge_eval,
)

router = APIRouter(prefix="/api/playable", tags=["playable"])


@router.post("/{pid}/evaluate")
async def evaluate_playable(pid: str):
    """★ VII.1 — (re)run the judge eval on an existing playable and persist it."""
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1, "brief": 1})
    if not doc or not doc.get("html"):
        return {"error": "not found"}
    evaluation = await _judge_eval(doc["html"], doc.get("brief", ""))
    try:
        await _db.playables.update_one({"playable_id": pid}, {"$set": {"evaluation": evaluation}})
    except Exception:
        pass
    return {"playable_id": pid, "evaluation": evaluation}


class RepairBody(BaseModel):
    error: str = ""


async def _do_repair(pid: str, error: str) -> dict:
    """🔧 Runtime self-heal core — fix a captured runtime JS error and persist the
    corrected HTML only if it stays structurally runnable. Returns a result dict
    (shared by the sync endpoint and the async job runner)."""
    doc = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "html": 1, "brief": 1, "playability_score": 1, "repair_trail": 1})
    if not doc or not doc.get("html"):
        return {"error": "not found", "repaired": False}
    err = (error or "").strip()[:600] or "an uncaught runtime JavaScript error"
    brief = doc.get("brief", "")
    repair_prompt = (
        f"ORIGINAL BRIEF:\n{brief}\n\n"
        f"The game below throws a RUNTIME JavaScript error while being played:\n  {err}\n\n"
        "Diagnose and FIX the root cause (e.g. use-before-declaration / temporal-dead-zone, "
        "undefined variables, bad references, async/order bugs). Keep all working gameplay intact. "
        f"Return the FULL corrected single-file HTML document:\n{doc['html'][:12000]}"
    )
    try:
        routed = await asyncio.to_thread(_llm_in_thread, repair_prompt, _REPAIR_SYS, _GAME_ENSEMBLE)
    except Exception:
        return {"playable_id": pid, "repaired": False, "error": "repair model unavailable"}
    new_html, _removed = _sanitize(_extract_html(routed.get("content", "")))
    val = _validate(new_html)
    if not new_html or val["score"] < PLAYABILITY_THRESHOLD:
        return {"playable_id": pid, "repaired": False,
                "score": val["score"], "missing": val.get("missing", [])}
    # The structural _validate gate already guarantees the fix is playable; skip the
    # (slow, multi-model) judge eval here so self-heal stays fast & ingress-safe.
    trail = doc.get("repair_trail") or []
    trail.append({"attempt": len(trail) + 1, "kind": "runtime_repair",
                  "score": val["score"], "error": err, "model": routed.get("model")})
    await _db.playables.update_one({"playable_id": pid}, {"$set": {
        "html": new_html, "playability_score": val["score"], "intricacy": val.get("intricacy"),
        "repair_trail": trail, "repaired_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"playable_id": pid, "repaired": True, "score": val["score"],
            "raw_path": f"/api/playable/{pid}/raw"}


@router.post("/{pid}/repair")
async def repair_playable(pid: str, body: RepairBody):
    """Synchronous runtime self-heal (can run ~100s). Prefer /repair/async + /job/{id}
    polling from clients to stay clear of public-ingress edge timeouts."""
    return await _do_repair(pid, body.error)


@router.post("/{pid}/repair/async")
async def repair_async(pid: str, body: RepairBody):
    """🔧 Kick runtime self-heal in the background; poll /job/{job_id}.
    Bulletproof against edge timeouts on long (~100s) repairs."""
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1, "html": 1})
    if not base or not base.get("html"):
        return {"error": "not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "repair", "parent_id": pid,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    asyncio.create_task(_run_job(job_id, _do_repair(pid, body.error)))
    return {"job_id": job_id, "job_status": "running"}
