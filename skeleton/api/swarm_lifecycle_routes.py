"""Lifecycle endpoints for pressure diagnostics and graceful worker maintenance."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from skeleton.agents.swarm_drain import drain, plan_drain
from skeleton.agents.swarm_gc import capacity
from skeleton.agents.swarm_pressure import classify_pressure
from skeleton.agents.swarm_runtime import SwarmRuntime

router = APIRouter(prefix="/swarm/lifecycle", tags=["swarm-lifecycle"])


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state
    state = get_state()
    if state.swarm is None:
        state.swarm = SwarmRuntime()
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
