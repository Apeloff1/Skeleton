"""
routes/director.py — Director Agent HTTP surface (Manifest Items 16, 17, 20).

  * GET  /api/galaxy-studio/director/{build_id}/state          (Item 16, debug)
  * GET  /api/galaxy-studio/director/{build_id}/plan/{stage}   (plan preview)
  * POST /api/galaxy-studio/director/{build_id}/reforge/{stage}(Item 17 — the
        single entry point for all Advanced re-forge requests; runs in a
        background task so the HTTP loop never blocks — Item 20)
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from core.director_agent import director

router = APIRouter(prefix="/api/galaxy-studio/director", tags=["director"])


class ValidateBody(BaseModel):
    artifact: object = {}


@router.post("/{build_id}/validate/{stage}")
async def director_validate(build_id: str, stage: str, body: ValidateBody):
    """Item 27 — run the headless Grounded Simulation Harness on an artifact and
    return its failure_rate / engagement_proxy / stability_score. The trace is
    cached for Director reflection.

    IMPROVEMENT (CNS→build loop): if the simulation FAILS the quality bar, the
    Director automatically reflects → queues this stage + its downstream cascade
    for re-forge, turning a simulation insight into a concrete build action."""
    from core.forge_validator import simulation_metrics, cache_trace
    metrics = simulation_metrics(stage, body.artifact)
    cache_trace(build_id, stage, metrics)
    reflection = None
    stability = int(metrics.get("stability_score", 0) or 0)
    if stability < 95:
        reflection = director.reflect_on_quality(build_id, {
            "stage": stage, "score": stability,
            "feedback": f"simulation stability {stability} (failure_rate {metrics.get('failure_rate')})"})
    return {"build_id": build_id, "stage": stage, "simulation": metrics,
            "auto_reflection": reflection}


@router.get("/{build_id}/state")
async def director_state(build_id: str):
    """Full Director world-state for a build (in-memory + ledger context)."""
    return director.get_state(build_id)


@router.get("/{build_id}/plan/{stage}")
async def director_plan(build_id: str, stage: str):
    """Preview the ordered plan (sub-forges + dependency cascade) for a stage."""
    return director.plan_stage(build_id, stage)


@router.post("/{build_id}/reforge/{stage}")
async def director_reforge(build_id: str, stage: str):
    """Item 17 — Director-owned re-forge. Plans the stage, reflects on its last
    quality score to build a delta instruction, then triggers the underlying
    forge as a background job. Non-blocking (Item 20)."""
    # Lazy imports to avoid a circular dependency at module load.
    from routes.game_kb import _FORGES, _stamped
    from routes.playable import _db, _run_job

    fn = _FORGES.get(stage)
    if not fn:
        return {"error": f"unknown stage '{stage}'", "forgeable": list(_FORGES)}

    g = await _db.playables.find_one({"playable_id": build_id}, {"_id": 0, "playable_id": 1})
    if not g:
        return {"error": "game not found"}

    plan = director.plan_stage(build_id, stage)

    # Reflect on the last known score for this stage to derive a delta note.
    st = director.get_state(build_id)
    last_score = st.get("quality_scores", {}).get(stage)
    reflection = director.reflect_on_quality(
        build_id, {"stage": stage, "score": last_score if last_score is not None else 0})
    delta = reflection.get("delta_instruction", "")

    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": f"director-reforge:{stage}",
        "parent_id": build_id, "director": True})
    # background task — does not block the HTTP response (Item 20)
    asyncio.create_task(_run_job(job_id, _stamped(build_id, stage, fn(build_id, delta))))
    return {
        "job_id": job_id, "job_status": "running", "stage": stage, "director": True,
        "plan": plan, "reflection": reflection,
    }
