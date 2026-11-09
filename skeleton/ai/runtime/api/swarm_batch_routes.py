"""Atomic bounded batch admission endpoints for swarm work."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from skeleton.agents.swarm_batch import submit_batch
from skeleton.agents.swarm_runtime import AdmissionError, SwarmRuntime, SwarmTask

router = APIRouter(prefix="/swarm/batch", tags=["swarm-batch"])


class BatchTask(BaseModel):
    task_id: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=-1_000_000, le=1_000_000)
    max_attempts: int = Field(default=3, ge=1, le=100)
    required_capabilities: list[str] = Field(default_factory=list, max_length=256)


class BatchSubmission(BaseModel):
    tasks: list[BatchTask] = Field(min_length=1, max_length=1_000)


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state

    state = get_state()
    if state.swarm is None:
        from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
        state.swarm = HardenedSwarmRuntime()
    return state.swarm


@router.post("/submit", status_code=status.HTTP_201_CREATED)
def submit(body: BatchSubmission, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    tasks = [
        SwarmTask(
            id=item.task_id,
            payload=item.payload,
            priority=item.priority,
            max_attempts=item.max_attempts,
            required_capabilities=frozenset(item.required_capabilities),
        )
        for item in body.tasks
    ]
    try:
        result = submit_batch(runtime, tasks)
    except AdmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"task_ids": list(result.task_ids), "admitted": result.admitted}
