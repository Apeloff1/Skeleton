"""Multi-tenant ingress policy endpoints for swarm workloads."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_quota import Quota

router = APIRouter(prefix="/swarm/ingress", tags=["swarm-ingress"])


class TenantConfiguration(BaseModel):
    weight: int = Field(default=1, ge=1, le=10_000)
    max_queued: int = Field(default=10_000, ge=1, le=10_000_000)
    max_leased: int = Field(default=1_000, ge=1, le=10_000_000)
    max_payload_bytes: int = Field(default=1_048_576, ge=1, le=1_000_000_000)


class IngressRequest(BaseModel):
    tenant: str = Field(min_length=1, max_length=200)
    task_id: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    cost: float = Field(default=1.0, gt=0, le=1_000_000)


class TaskAccountingRequest(BaseModel):
    tenant: str = Field(min_length=1, max_length=200)
    task_id: str = Field(min_length=1, max_length=300)


def _governor() -> SwarmIngressGovernor:
    from skeleton.api.server import get_state

    state = get_state()
    governor = getattr(state, "swarm_ingress", None)
    if governor is None:
        governor = SwarmIngressGovernor()
        state.swarm_ingress = governor
    return governor


@router.get("/status")
def ingress_status(governor: SwarmIngressGovernor = Depends(_governor)) -> dict[str, object]:
    return governor.status()


@router.put("/tenants/{tenant}")
def configure_tenant(
    tenant: str,
    body: TenantConfiguration,
    governor: SwarmIngressGovernor = Depends(_governor),
) -> dict[str, object]:
    try:
        governor.configure_tenant(
            tenant,
            quota=Quota(body.max_queued, body.max_leased, body.max_payload_bytes),
            weight=body.weight,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"tenant": tenant.strip(), "configured": True, "status": governor.status()}


@router.post("/admit", status_code=status.HTTP_201_CREATED)
def admit(
    body: IngressRequest,
    governor: SwarmIngressGovernor = Depends(_governor),
) -> dict[str, object]:
    try:
        decision = governor.admit(body.tenant, body.task_id, body.payload, cost=body.cost)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not decision.accepted:
        raise HTTPException(status_code=429 if decision.reason == "rate limit exceeded" else 409, detail=asdict(decision))
    return asdict(decision)


@router.post("/lease")
def mark_leased(
    body: TaskAccountingRequest,
    governor: SwarmIngressGovernor = Depends(_governor),
) -> dict[str, object]:
    try:
        governor.mark_leased(body.tenant, body.task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"tenant": body.tenant.strip(), "task_id": body.task_id.strip(), "phase": "leased"}


@router.post("/complete")
def complete(
    body: TaskAccountingRequest,
    governor: SwarmIngressGovernor = Depends(_governor),
) -> dict[str, object]:
    try:
        governor.complete(body.tenant, body.task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"tenant": body.tenant.strip(), "task_id": body.task_id.strip(), "completed": True}
