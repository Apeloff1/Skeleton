"""Supervisor endpoints for quarantine, circuits and dispatch previews."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.agents.swarm_supervisor import SwarmSupervisor

router = APIRouter(prefix="/swarm/supervisor", tags=["swarm-supervisor"])


class DispatchRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=300)
    priority: int = Field(default=100, ge=-1_000_000, le=1_000_000)
    required_capabilities: list[str] = Field(default_factory=list, max_length=256)


class QuarantineRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2_000)
    seconds: float | None = Field(default=None, gt=0, le=604_800)


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state

    state = get_state()
    if state.swarm is None:
        from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
        state.swarm = HardenedSwarmRuntime()
    return state.swarm


def _supervisor() -> SwarmSupervisor:
    from skeleton.api.server import get_state

    state = get_state()
    supervisor = getattr(state, "swarm_supervisor", None)
    if supervisor is None:
        supervisor = SwarmSupervisor()
        state.swarm_supervisor = supervisor
    broker = getattr(state, "swarm_broker", None)
    if broker is not None and broker.supervisor is not supervisor:
        broker.supervisor = supervisor
    return supervisor


def _resolve_supervisor(value: object) -> SwarmSupervisor:
    return value if isinstance(value, SwarmSupervisor) else _supervisor()


@router.get("/status")
def status(supervisor: SwarmSupervisor = Depends(_supervisor)) -> dict[str, object]:
    return _resolve_supervisor(supervisor).status()


@router.post("/dispatch-preview")
def dispatch_preview(
    body: DispatchRequest,
    runtime: SwarmRuntime = Depends(_runtime),
    supervisor: SwarmSupervisor = Depends(_supervisor),
) -> dict[str, object]:
    supervisor = _resolve_supervisor(supervisor)
    task = SwarmTask(
        body.task_id,
        {},
        priority=body.priority,
        required_capabilities=frozenset(body.required_capabilities),
    )
    return asdict(supervisor.dispatch(runtime, task))


@router.post("/workers/{worker_id}/quarantine")
def quarantine(
    worker_id: str,
    body: QuarantineRequest,
    runtime: SwarmRuntime = Depends(_runtime),
    supervisor: SwarmSupervisor = Depends(_supervisor),
) -> dict[str, object]:
    supervisor = _resolve_supervisor(supervisor)
    if runtime.worker(worker_id) is None:
        raise HTTPException(status_code=404, detail="worker not found")
    supervisor.quarantine_worker(worker_id, reason=body.reason, seconds=body.seconds)
    return {"worker_id": worker_id, "quarantined": True, "status": supervisor.status()}


@router.delete("/workers/{worker_id}/quarantine")
def release(
    worker_id: str,
    supervisor: SwarmSupervisor = Depends(_supervisor),
) -> dict[str, object]:
    supervisor = _resolve_supervisor(supervisor)
    released = supervisor.release_worker(worker_id)
    if not released:
        raise HTTPException(status_code=404, detail="worker not quarantined")
    return {"worker_id": worker_id, "released": True}


@router.post("/workers/{worker_id}/failure")
def record_failure(
    worker_id: str,
    supervisor: SwarmSupervisor = Depends(_supervisor),
) -> dict[str, object]:
    supervisor = _resolve_supervisor(supervisor)
    supervisor.record_failure(worker_id)
    return {"worker_id": worker_id, "status": supervisor.status()}


@router.post("/workers/{worker_id}/success")
def record_success(
    worker_id: str,
    supervisor: SwarmSupervisor = Depends(_supervisor),
) -> dict[str, object]:
    supervisor = _resolve_supervisor(supervisor)
    supervisor.record_success(worker_id)
    return {"worker_id": worker_id, "status": supervisor.status()}
