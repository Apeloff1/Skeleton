"""
✨ ONE-TAP POLISH — chain the three game-code "wire" passes into one guided upgrade.

Runs, in sequence on a single generated game: SENTIENCE (living NPC AI) → PHYSICS
(deterministic Verlet engine) → AESTHETICS (neural post-FX + adaptive audio). Each
step reads the latest persisted HTML (so engines compose), is runnability-gated, and
persists independently — a step that can't apply safely is skipped without corrupting
the game. The job reports per-step progress so the UI can show a live checklist.
"""
from __future__ import annotations

import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter

from routes.playable import _db, _run_job
from routes.playable_sentience import _do_sentience
from routes.playable_physics import _do_physics
from routes.playable_aesthetics import _do_aesthetics

router = APIRouter(prefix="/api/playable", tags=["playable"])

_STEPS = [
    ("sentience", "👾 Living NPCs", _do_sentience),
    ("physics", "🧲 Physics", _do_physics),
    ("aesthetics", "🎨 FX + Audio", _do_aesthetics),
]


async def _do_polish(pid: str, job_id: str) -> dict:
    applied: list[str] = []
    skipped: list[str] = []
    steps: list[dict] = []
    final_version = None
    final_score = None
    for i, (kind, label, fn) in enumerate(_STEPS):
        await _db.playable_jobs.update_one({"job_id": job_id}, {"$set": {
            "step": i + 1, "step_total": len(_STEPS), "step_kind": kind, "step_label": label,
        }})
        try:
            res = await fn(pid)
        except Exception as e:  # a single step failing must not abort the chain
            res = {"applied": False, "error": str(e)[:160]}
        ok = bool(res.get("applied"))
        (applied if ok else skipped).append(kind)
        if ok:
            final_version = res.get("version", final_version)
            final_score = res.get("score", final_score)
        steps.append({"kind": kind, "label": label, "applied": ok,
                      "score": res.get("score"), "error": res.get("error")})
    return {
        "playable_id": pid, "kind": "polish", "applied": applied, "skipped": skipped,
        "steps": steps, "version": final_version, "score": final_score,
        "count": len(applied), "raw_path": f"/api/playable/{pid}/raw",
    }


@router.post("/{pid}/polish/async")
async def polish_async(pid: str):
    """✨ One-tap AAA polish: chain Sentience → Physics → Aesthetics on this game.
    Async + long-running (~6-12 min); poll /job/{job_id} — result carries applied[], steps[]."""
    from core.anti_farm import allow
    if not allow(f"polish:{pid}", rate_per_sec=0.05, burst=2):
        return {"error": "rate_limited", "detail": "A polish run is already in flight — give it a few minutes."}
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1})
    if not base or not base.get("html"):
        return {"error": "not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "polish", "parent_id": pid,
        "step": 0, "step_total": len(_STEPS),
        "created_at": datetime.now(timezone.utc).isoformat()})
    asyncio.create_task(_run_job(job_id, _do_polish(pid, job_id)))
    return {"job_id": job_id, "job_status": "running", "steps": [s[0] for s in _STEPS]}
