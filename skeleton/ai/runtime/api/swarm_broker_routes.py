"""Unified bounded submission, dispatch and completion endpoints for swarm execution."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_runtime import AdmissionError, LeaseError, SwarmRuntime, SwarmTask

router = APIRouter(prefix="/swarm/broker", tags=["swarm-broker"])


class BrokerSubmission(BaseModel):
    task_id: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=-1_000_000, le=1_000_000)
    max_attempts: int = Field(default=3, ge=1, le=100)
    required_capabilities: list[str] = Field(default_factory=list, max_length=256)
    idempotency_key: str | None = Field(default=None, max_length=500)


class BrokerCompletion(BaseModel):
    completion_token: str | None = Field(default=None, min_length=1, max_length=500)


class BrokerFailure(BrokerCompletion):
    error: str = Field(min_length=1, max_length=2_000)


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state

    state = get_state()
    if state.swarm is None:
        from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
        state.bind_swarm_runtime(HardenedSwarmRuntime())
    return state.swarm


def _broker(runtime: SwarmRuntime = Depends(_runtime)) -> SwarmBroker:
    from skeleton.api.server import get_state

    state = get_state()
    broker = getattr(state, "swarm_broker", None)
    if broker is None or broker.runtime is not runtime:
        state.bind_swarm_runtime(runtime)
        broker = state.swarm_broker
    return broker


@router.get("/status")
def broker_status(broker: SwarmBroker = Depends(_broker)) -> dict[str, Any]:
    snapshot = broker.runtime.snapshot()
    return {
        "snapshot": asdict(snapshot),
        "supervisor": broker.supervisor.status(),
        "idempotency_entries": len(broker.control.idempotency),
        "completion_entries": len(broker.completions),
    }


@router.post("/submit", status_code=status.HTTP_201_CREATED)
def submit_and_dispatch(body: BrokerSubmission, broker: SwarmBroker = Depends(_broker)) -> dict[str, Any]:
    try:
        result = broker.submit_and_dispatch(
            SwarmTask(
                id=body.task_id,
                payload=body.payload,
                priority=body.priority,
                max_attempts=body.max_attempts,
                required_capabilities=frozenset(body.required_capabilities),
            ),
            idempotency_key=body.idempotency_key,
        )
    except AdmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return asdict(result)


@router.post("/workers/{worker_id}/tasks/{task_id}/success")
def complete(
    worker_id: str,
    task_id: str,
    body: BrokerCompletion | None = None,
    broker: SwarmBroker = Depends(_broker),
) -> dict[str, Any]:
    try:
        result = broker.record_success(
            worker_id,
            task_id,
            completion_token=body.completion_token if body else None,
        )
    except LeaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "task_id": result.task.id,
        "state": result.task.state.value,
        "worker_id": worker_id,
        "duplicate": result.duplicate,
    }


@router.post("/workers/{worker_id}/tasks/{task_id}/failure")
def fail(worker_id: str, task_id: str, body: BrokerFailure, broker: SwarmBroker = Depends(_broker)) -> dict[str, Any]:
    try:
        result = broker.record_failure(
            worker_id,
            task_id,
            body.error,
            completion_token=body.completion_token,
        )
    except LeaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "task_id": result.task.id,
        "state": result.task.state.value,
        "worker_id": worker_id,
        "attempts": result.task.attempts,
        "duplicate": result.duplicate,
    }
