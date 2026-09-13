"""Operator-facing diagnostics and maintenance endpoints for the swarm runtime."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from skeleton.agents.swarm_autoscale import AutoscalePolicy
from skeleton.agents.swarm_maintenance import compact_state
from skeleton.agents.swarm_operator import SwarmOperator
from skeleton.agents.swarm_runtime import SwarmRuntime
from skeleton.agents.swarm_snapshot import SnapshotError, normalize_snapshot

router = APIRouter(prefix="/swarm/operator", tags=["swarm-operator"])


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state
    state = get_state()
    if state.swarm is None:
        state.swarm = SwarmRuntime()
    return state.swarm


@router.get("/overview")
def overview(
    stale_after: float = Query(default=90.0, gt=0, le=86_400),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    return SwarmOperator(runtime).overview(stale_after=stale_after)


@router.get("/hot-workers")
def hot_workers(
    utilization: float = Query(default=0.8, ge=0, le=1),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    return {"workers": SwarmOperator(runtime).hot_workers(utilization_at_least=utilization)}


@router.get("/autoscale")
def autoscale(
    target_tasks_per_slot: float = Query(default=2.0, gt=0),
    min_slots: int = Query(default=1, ge=0),
    max_slots: int = Query(default=10_000, ge=1),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        policy = AutoscalePolicy(target_tasks_per_slot, min_slots, max_slots)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(policy.recommend(runtime))


@router.get("/snapshot/normalized")
def normalized_snapshot(runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return normalize_snapshot(runtime.export_state())
    except SnapshotError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/snapshot/compact")
def compact_snapshot(
    max_terminal_tasks: int = Query(default=10_000, ge=0, le=1_000_000),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    return compact_state(runtime, max_terminal_tasks=max_terminal_tasks)
