"""Policy and scheduling projections for swarm operators and clients."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from skeleton.agents.swarm_admission import AdmissionPolicy
from skeleton.agents.swarm_control import SwarmControlPlane
from skeleton.agents.swarm_runtime import AdmissionError, SwarmRuntime, SwarmTask

router = APIRouter(prefix="/swarm/policy", tags=["swarm-policy"])


class AdmissionPreview(BaseModel):
    task_id: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    max_attempts: int = Field(default=3, ge=1, le=100)
    required_capabilities: list[str] = Field(default_factory=list, max_length=256)
    max_queue_pressure: float = Field(default=100.0, gt=0)
    require_capability_route: bool = False
    reject_when_no_workers: bool = False


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state
    state = get_state()
    if state.swarm is None:
        state.swarm = SwarmRuntime()
    return state.swarm


def _task(body: AdmissionPreview) -> SwarmTask:
    return SwarmTask(
        body.task_id,
        body.payload,
        priority=body.priority,
        max_attempts=body.max_attempts,
        required_capabilities=frozenset(body.required_capabilities),
    )


@router.post("/admission-preview")
def admission_preview(body: AdmissionPreview, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    policy = AdmissionPolicy(
        max_queue_pressure=body.max_queue_pressure,
        require_capability_route=body.require_capability_route,
        reject_when_no_workers=body.reject_when_no_workers,
    )
    return asdict(policy.evaluate(runtime, _task(body)))


@router.get("/tasks/{task_id}/worker-ranking")
def worker_ranking(task_id: str, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        ranked = SwarmControlPlane(runtime).rank_workers(task_id)
    except AdmissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"task_id": task_id, "workers": [asdict(item) for item in ranked]}
