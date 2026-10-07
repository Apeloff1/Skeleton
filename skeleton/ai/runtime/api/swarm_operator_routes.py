"""Operator-facing diagnostics and maintenance endpoints for the swarm runtime."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from skeleton.agents.swarm_autoscale import AutoscalePolicy
from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_failover import ReplicaState
from skeleton.agents.swarm_gc import capacity, compact_runtime
from skeleton.agents.swarm_maintenance import compact_state
from skeleton.agents.swarm_operator import SwarmOperator
from skeleton.agents.swarm_queries import query_tasks
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_retention import RetentionPolicy, prune_terminal
from skeleton.agents.swarm_runtime import AdmissionError, SwarmRuntime, TaskState
from skeleton.agents.swarm_slo import SLOPolicy
from skeleton.agents.swarm_snapshot import SnapshotError, normalize_snapshot
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker
from skeleton.agents.swarm_tenant_checkpoint import TenantCheckpointStore
from skeleton.api.swarm_recovery_service import activate_recovery

router = APIRouter(prefix="/swarm/operator", tags=["swarm-operator"])


class ReplicaReport(BaseModel):
    replica_id: str = Field(min_length=1, max_length=200)
    epoch: int = Field(ge=0)
    sequence: int = Field(ge=0)
    healthy: bool = True


class FailoverRequest(BaseModel):
    replicas: list[ReplicaReport] = Field(default_factory=list, max_length=1024)


def _state():
    from skeleton.api.server import get_state
    return get_state()


def _runtime() -> SwarmRuntime:
    state = _state()
    if state.swarm is None:
        from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
        state.bind_swarm_runtime(HardenedSwarmRuntime())
    return state.swarm


def _recovery() -> SwarmRecoveryManager:
    state = _state()
    if getattr(state, "swarm_recovery", None) is None:
        state.swarm_recovery = SwarmRecoveryManager(max_checkpoints=16)
    return state.swarm_recovery


def _stage_tenant_bundle(
    runtime: SwarmRuntime,
    current_tenant: TenantSwarmBroker,
) -> tuple[Any, SwarmBroker, TenantSwarmBroker]:
    state = _state()
    staged_ingress = current_tenant.ingress.fork_empty()
    staged_broker = SwarmBroker(runtime, supervisor=state.swarm_supervisor)
    staged_tenant = TenantSwarmBroker(
        staged_broker,
        staged_ingress,
        max_terminal_records=current_tenant.max_terminal_records,
    )
    return staged_ingress, staged_broker, staged_tenant


def _stage_live_metadata_restore(runtime: SwarmRuntime) -> dict[str, Any] | None:
    """Carry current tenant ownership across runtime replacement with generation fencing."""
    state = _state()
    current_tenant = getattr(state, "swarm_tenant_broker", None)
    if current_tenant is None:
        return None

    with current_tenant._lock:
        current_tenant._assert_active()
        staged_ingress, staged_broker, staged_tenant = _stage_tenant_bundle(runtime, current_tenant)
        transient = TenantCheckpointStore(max_checkpoints=1)
        transient.capture(1, current_tenant)
        repair = transient.restore(staged_tenant, 1)
        state.commit_swarm_bundle(runtime, staged_broker, staged_ingress, staged_tenant)
        return asdict(repair)


def _publish_runtime(runtime: SwarmRuntime) -> dict[str, Any] | None:
    """Publish a replacement runtime atomically with tenant metadata when present."""
    tenant_repair = _stage_live_metadata_restore(runtime)
    if tenant_repair is None:
        _state().bind_swarm_runtime(runtime)
    return tenant_repair


def _task_record(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "state": task.state.value,
        "priority": task.priority,
        "attempts": task.attempts,
        "max_attempts": task.max_attempts,
        "leased_to": task.leased_to,
        "required_capabilities": sorted(task.required_capabilities),
    }


@router.get("/overview")
def overview(stale_after: float = Query(default=90.0, gt=0, le=86_400), runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    data = SwarmOperator(runtime).overview(stale_after=stale_after)
    data["capacity"] = capacity(runtime)
    return data


@router.get("/hot-workers")
def hot_workers(utilization: float = Query(default=0.8, ge=0, le=1), runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    return {"workers": SwarmOperator(runtime).hot_workers(utilization_at_least=utilization)}


@router.get("/autoscale")
def autoscale(target_tasks_per_slot: float = Query(default=2.0, gt=0), min_slots: int = Query(default=1, ge=0), max_slots: int = Query(default=10_000, ge=1), runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        policy = AutoscalePolicy(target_tasks_per_slot, min_slots, max_slots)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(policy.recommend(runtime))


@router.get("/slo")
def slo(max_dead_ratio: float = Query(default=0.01, ge=0, le=1), max_queue_per_slot: float = Query(default=50.0, gt=0), min_available_slots: int = Query(default=1, ge=0), runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    return SLOPolicy(max_dead_ratio, max_queue_per_slot, min_available_slots).evaluate(runtime)


@router.get("/tasks")
def tasks(state: str | None = Query(default=None), capability: str | None = Query(default=None), offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=10_000), runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    states = None
    if state is not None:
        try:
            states = [TaskState(state)]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"invalid task state: {state}") from exc
    page = query_tasks(runtime, states=states, capability=capability, offset=offset, limit=limit)
    return {"items": [_task_record(task) for task in page.items], "total": page.total, "offset": page.offset, "limit": page.limit}


@router.get("/snapshot/normalized")
def normalized_snapshot(runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return normalize_snapshot(runtime.export_state())
    except SnapshotError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/snapshot/compact")
def compact_snapshot(max_terminal_tasks: int = Query(default=10_000, ge=0, le=1_000_000), runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    return compact_state(runtime, max_terminal_tasks=max_terminal_tasks)


@router.post("/prune-terminal")
def prune_terminal_tasks(
    keep_terminal: int = Query(default=10_000, ge=0, le=1_000_000),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    plan = RetentionPolicy(max_terminal_tasks=keep_terminal).plan(runtime)
    before = capacity(runtime)
    try:
        removed = prune_terminal(runtime, plan.removable)
    except (AdmissionError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "removed": removed,
        "planned": len(plan.removable),
        "retained_terminal": plan.retained,
        "terminal_before": plan.terminal,
        "capacity_before": before,
        "capacity_after": capacity(runtime),
    }


@router.post("/gc")
def gc(keep_terminal: int = Query(default=10_000, ge=0, le=1_000_000), runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    rebuilt, result = compact_runtime(runtime, keep_terminal=keep_terminal)
    try:
        tenant_repair = _publish_runtime(rebuilt)
    except (AdmissionError, KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=f"staged compaction rejected: {exc}") from exc
    result_payload = asdict(result)
    result_payload["removed_terminal"] = result.removed
    return {"result": result_payload, "tenant_repair": tenant_repair, "capacity": capacity(rebuilt), "snapshot": asdict(rebuilt.snapshot())}


@router.post("/checkpoint")
def checkpoint(runtime: SwarmRuntime = Depends(_runtime), recovery: SwarmRecoveryManager = Depends(_recovery)) -> dict[str, Any]:
    tenant_broker = getattr(_state(), "swarm_tenant_broker", None)
    sequence = recovery.checkpoint(runtime, tenant_broker)
    return {"sequence": sequence, "status": asdict(recovery.status())}


@router.post("/restore-latest")
def restore_latest(recovery: SwarmRecoveryManager = Depends(_recovery)) -> dict[str, Any]:
    sequence = recovery.status().latest_sequence
    if sequence is None:
        raise HTTPException(status_code=404, detail="no checkpoint available")
    try:
        result = activate_recovery(_state(), recovery, sequence)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (AdmissionError, TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=f"staged restore rejected: {exc}") from exc
    runtime = _state().swarm
    return {
        "restored": True,
        "tenant_repair": result.tenant_repair,
        "status": asdict(recovery.status()),
        "snapshot": asdict(runtime.snapshot()),
    }


@router.post("/failover/elect")
def elect_failover(body: FailoverRequest, recovery: SwarmRecoveryManager = Depends(_recovery)) -> dict[str, Any]:
    replicas = {item.replica_id: ReplicaState(item.replica_id, item.epoch, item.sequence, item.healthy) for item in body.replicas}
    leader = recovery.elect(replicas)
    return {"leader": leader, "status": asdict(recovery.status())}


@router.get("/recovery")
def recovery_status(recovery: SwarmRecoveryManager = Depends(_recovery)) -> dict[str, Any]:
    return asdict(recovery.status())
