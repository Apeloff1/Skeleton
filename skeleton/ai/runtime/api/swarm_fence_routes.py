"""Attempt-aware lease mutation endpoints for stale-request protection."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from skeleton.agents.swarm_fencing import LeaseFence, fenced_fail, fenced_renew, fenced_succeed
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import LeaseError, SwarmRuntime

router = APIRouter(prefix="/swarm/fenced", tags=["swarm-fenced"])


class FencedFailure(BaseModel):
    attempt: int = Field(ge=1)
    error: str = Field(min_length=1, max_length=2_000)


class FencedCompletion(BaseModel):
    attempt: int = Field(ge=1)


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state
    state = get_state()
    if state.swarm is None:
        state.swarm = HardenedSwarmRuntime()
    return state.swarm


def _task(task: Any) -> dict[str, Any]:
    data = asdict(task)
    data["state"] = task.state.value
    data["required_capabilities"] = sorted(task.required_capabilities)
    data["payload"] = dict(task.payload)
    return data


@router.post("/workers/{worker_id}/tasks/{task_id}/success")
def succeed(
    worker_id: str,
    task_id: str,
    body: FencedCompletion,
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        return _task(fenced_succeed(runtime, LeaseFence(task_id, worker_id, body.attempt, None)))
    except LeaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workers/{worker_id}/tasks/{task_id}/failure")
def fail(
    worker_id: str,
    task_id: str,
    body: FencedFailure,
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        return _task(fenced_fail(runtime, LeaseFence(task_id, worker_id, body.attempt, None), body.error))
    except LeaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workers/{worker_id}/tasks/{task_id}/renew")
def renew(
    worker_id: str,
    task_id: str,
    attempt: int = Query(ge=1),
    seconds: float | None = Query(default=None, gt=0, le=86_400),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        return _task(fenced_renew(runtime, LeaseFence(task_id, worker_id, attempt, None), seconds=seconds))
    except LeaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
