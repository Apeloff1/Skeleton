"""Lifecycle endpoints for pressure diagnostics and graceful worker maintenance."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from skeleton.agents.swarm_drain import drain, plan_drain
from skeleton.agents.swarm_gc import capacity
from skeleton.agents.swarm_janitor import reap_stale_workers
from skeleton.agents.swarm_pressure import classify_pressure
from skeleton.agents.swarm_runtime import SwarmRuntime

router = APIRouter(prefix="/swarm/lifecycle", tags=["swarm-lifecycle"])


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state
    state = get_state()
    if state.swarm is None:
        from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
        state.swarm = HardenedSwarmRuntime()
    return state.swarm


@router.get("/pressure")
def pressure(runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    return {"pressure": asdict(classify_pressure(runtime)), "capacity": capacity(runtime)}


@router.get("/workers/{worker_id}/drain")
def drain_preview(worker_id: str, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return asdict(plan_drain(runtime, worker_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="worker not found") from exc


@router.post("/workers/{worker_id}/drain")
def execute_drain(
    worker_id: str,
    force: bool = Query(default=False),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        plan = drain(runtime, worker_id, force=force)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="worker not found") from exc
    executed = runtime.worker(worker_id) is None
    return {"executed": executed, "force": force, "plan": asdict(plan)}


@router.post("/workers/reap-stale")
def reap_stale(
    stale_after: float = Query(default=90.0, gt=0, le=604800),
    requeue: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=1000),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    result = reap_stale_workers(runtime, stale_after=stale_after, requeue=requeue, limit=limit)
    return {"result": asdict(result), "snapshot": asdict(runtime.snapshot())}
