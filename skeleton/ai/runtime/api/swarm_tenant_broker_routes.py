"""Tenant-aware submission and completion endpoints for swarm execution."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from skeleton.agents.swarm_runtime import AdmissionError, LeaseError, SwarmTask
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker

router = APIRouter(prefix="/swarm/tenant-broker", tags=["swarm-tenant-broker"])


class TenantSubmission(BaseModel):
    tenant: str = Field(min_length=1, max_length=200)
    task_id: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=-1_000_000, le=1_000_000)
    max_attempts: int = Field(default=3, ge=1, le=100)
    required_capabilities: list[str] = Field(default_factory=list, max_length=256)
    idempotency_key: str | None = Field(default=None, max_length=500)
    cost: float = Field(default=1.0, gt=0, le=1_000_000)


class TenantCompletion(BaseModel):
    completion_token: str | None = Field(default=None, max_length=500)


class TenantFailure(TenantCompletion):
    error: str = Field(min_length=1, max_length=2_000)


def _tenant_broker() -> TenantSwarmBroker:
    from skeleton.api.server import get_state

    state = get_state()
    broker = getattr(state, "swarm_tenant_broker", None)
    if broker is None:
        if state.swarm is None:
            from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
            state.bind_swarm_runtime(HardenedSwarmRuntime())
        from skeleton.agents.swarm_ingress import SwarmIngressGovernor
        ingress = getattr(state, "swarm_ingress", None) or SwarmIngressGovernor()
        if hasattr(state, "bind_swarm_ingress"):
            state.bind_swarm_ingress(ingress)
            broker = state.swarm_tenant_broker
        else:
            state.swarm_ingress = ingress
            broker = TenantSwarmBroker(state.swarm_broker, ingress)
            state.swarm_tenant_broker = broker
    return broker


@router.get("/status")
def tenant_broker_status(broker: TenantSwarmBroker = Depends(_tenant_broker)) -> dict[str, object]:
    return broker.status()


@router.get("/reconcile")
def reconcile(broker: TenantSwarmBroker = Depends(_tenant_broker)) -> dict[str, tuple[str, ...]]:
    return broker.reconcile()


@router.post("/reconcile/repair")
def repair(broker: TenantSwarmBroker = Depends(_tenant_broker)) -> dict[str, object]:
    result = broker.repair()
    return {"repair": asdict(result), "reconcile": broker.reconcile(), "status": broker.status()}


@router.post("/submit", status_code=status.HTTP_201_CREATED)
def submit(body: TenantSubmission, broker: TenantSwarmBroker = Depends(_tenant_broker)) -> dict[str, object]:
    try:
        result = broker.submit_and_dispatch(
            body.tenant,
            SwarmTask(
                id=body.task_id,
                payload=body.payload,
                priority=body.priority,
                max_attempts=body.max_attempts,
                required_capabilities=frozenset(body.required_capabilities),
            ),
            idempotency_key=body.idempotency_key,
            cost=body.cost,
        )
    except (AdmissionError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result.admitted:
        code = 429 if result.reason == "rate limit exceeded" else 409
        raise HTTPException(status_code=code, detail=asdict(result))
    return asdict(result)


@router.post("/workers/{worker_id}/tasks/{task_id}/success")
def succeed(worker_id: str, task_id: str, body: TenantCompletion, broker: TenantSwarmBroker = Depends(_tenant_broker)) -> dict[str, object]:
    try:
        result = broker.record_success(worker_id, task_id, completion_token=body.completion_token)
    except (AdmissionError, LeaseError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "task_id": result.task.id,
        "state": result.task.state.value,
        "worker_id": worker_id,
        "duplicate": result.duplicate,
        "tenant": broker.tenant_for(task_id),
    }


@router.post("/workers/{worker_id}/tasks/{task_id}/failure")
def fail(worker_id: str, task_id: str, body: TenantFailure, broker: TenantSwarmBroker = Depends(_tenant_broker)) -> dict[str, object]:
    try:
        result = broker.record_failure(worker_id, task_id, body.error, completion_token=body.completion_token)
    except (AdmissionError, LeaseError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "task_id": result.task.id,
        "state": result.task.state.value,
        "worker_id": worker_id,
        "duplicate": result.duplicate,
        "tenant": broker.tenant_for(task_id),
        "attempts": result.task.attempts,
    }
