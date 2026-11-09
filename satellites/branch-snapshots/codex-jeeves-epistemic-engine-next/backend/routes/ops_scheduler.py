"""
routes/ops_scheduler.py — Stage E ops surface: scheduler + per-capability SLOs.
"""
from __future__ import annotations

import time
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/scheduler")
async def scheduler():
    from core.scheduler import scheduler_status
    return {"ok": True, **scheduler_status()}


class RunJobReq(BaseModel):
    job_id: str


@router.post("/scheduler/run")
async def scheduler_run(req: RunJobReq):
    from core.scheduler import run_job_now
    return await run_job_now(req.job_id)


@router.get("/slo")
async def slo():
    """Per-capability SLO snapshot: probe each core capability and report a
    latency + health verdict against a target budget."""
    import asyncio
    budgets = {  # ms budget per capability
        "coverage": 3000, "readiness": 4000, "fabric": 2000,
        "lafs_recall": 2500, "quorum": 1500, "legions": 2500,
    }
    from routes.gameforge_coverage import selftest as _cov
    from routes.prood import readiness as _rdy, run_quorum as _q, QuorumRequest
    from routes.omega_conductor import fabric_overview as _fab, legions_roster as _lg
    from routes.lafs import recall as _recall, RecallReq

    async def _timed(name, coro):
        t0 = time.time()
        ok = True
        try:
            await coro
        except Exception:  # noqa: BLE001
            ok = False
        ms = round((time.time() - t0) * 1000, 1)
        budget = budgets.get(name, 3000)
        return name, {"ms": ms, "budget_ms": budget, "ok": ok,
                      "within_slo": ok and ms <= budget}

    probes = [
        _timed("coverage", _cov()),
        _timed("readiness", _rdy()),
        _timed("fabric", _fab()),
        _timed("quorum", _q(QuorumRequest(value="slo", n=7, f=2))),
        _timed("legions", _lg()),
        _timed("lafs_recall", _recall(RecallReq(query="pathfinding", top_k=3))),
    ]
    results = dict(await asyncio.gather(*probes))
    met = sum(1 for v in results.values() if v["within_slo"])
    return {"ok": True, "capabilities": len(results), "within_slo": met,
            "slo_percent": round(100.0 * met / max(1, len(results)), 1),
            "detail": results}
