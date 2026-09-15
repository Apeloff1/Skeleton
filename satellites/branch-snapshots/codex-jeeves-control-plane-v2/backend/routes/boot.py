"""
routes/boot.py — SOTA boot observability endpoints (Feb 2026).

  GET /api/health/boot/timeline        → ring-buffer of events
  GET /api/health/boot/score           → weighted boot score + counts
  GET /api/health/boot/stages          → every stage with status + timing
  POST /api/health/boot/replay/{name}  → manually re-run a stage (idempotent)

These complement the existing /api/health/boot endpoint from server.py
(which lives in the lifespan _kick registry) without removing it.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Any

from core import boot_stages, boot_timeline

router = APIRouter(tags=["BootObservability"], prefix="/health/boot")


@router.get("/timeline")
async def get_timeline(
    limit: int = Query(default=200, ge=1, le=2000),
    after_ts: float | None = Query(default=None),
) -> dict[str, Any]:
    return {
        "ok": True,
        "stats": boot_timeline.stats(),
        "events": boot_timeline.recent(limit=limit, after_ts=after_ts),
    }


@router.get("/score")
async def get_boot_score() -> dict[str, Any]:
    summary = boot_stages.registry().summary()
    return {
        "ok": summary["ok"],
        "boot_score": summary["boot_score"],
        "counts": summary["counts"],
        "critical_ok": summary["critical_ok"],
        "elapsed_s": summary["elapsed_s"],
    }


@router.get("/stages")
async def get_stages(phase_max: int | None = Query(default=None, ge=0, le=3)) -> dict[str, Any]:
    summary = boot_stages.registry().summary(max_phase=phase_max)
    return {"ok": True, **summary}


@router.post("/replay/{name}")
async def replay_stage(name: str) -> dict[str, Any]:
    reg = boot_stages.registry()
    if name not in reg._stages:  # noqa: SLF001  — explicit private read for admin
        raise HTTPException(status_code=404, detail="stage not found")
    st = reg._stages[name]      # noqa: SLF001
    # Reset transient fields so the replay produces a fresh row.
    st.status = boot_stages.STATUS_PENDING
    st.attempts = 0
    st.started_at = None
    st.ended_at = None
    st.error = None
    st.result = None
    await reg._run_stage(st)    # noqa: SLF001
    return {"ok": st.status == boot_stages.STATUS_OK, "stage": st.snapshot()}
