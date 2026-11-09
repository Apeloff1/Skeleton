"""HTTP control plane for the bounded in-process swarm runtime."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import AdmissionError, LeaseError, SwarmRuntime, SwarmTask, TaskState

router = APIRouter(prefix="/swarm", tags=["swarm"])


class WorkerRegistration(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200)
    capabilities: list[str] = Field(default_factory=list, max_length=256)
    capacity: int = Field(default=1, ge=1, le=10_000)


class TaskSubmission(BaseModel):
    task_id: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=-1_000_000, le=1_000_000)
    max_attempts: int = Field(default=3, ge=1, le=100)
    required_capabilities: list[str] = Field(default_factory=list, max_length=256)


class FailureReport(BaseModel):
    error: str = Field(min_length=1, max_length=20_000)


class CancelRequest(BaseModel):
    reason: str = Field(default="cancelled", min_length=1, max_length=2_000)


class ReviveRequest(BaseModel):
    reset_attempts: bool = False


class RestoreRequest(BaseModel):
    state: dict[str, Any]
    requeue_leased: bool = True


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state
    state = get_state()
    runtime = getattr(state, "swarm", None)
    if runtime is None:
        runtime = HardenedSwarmRuntime()
        state.bind_swarm_runtime(runtime)
    return runtime


def _replace_runtime(runtime: SwarmRuntime) -> None:
    from skeleton.api.server import get_state
    get_state().bind_swarm_runtime(runtime)


def _task_dict(task: SwarmTask) -> dict[str, Any]:
    data = asdict(task)
    data["state"] = task.state.value
    data["required_capabilities"] = sorted(task.required_capabilities)
    data["payload"] = dict(task.payload)
    return data


def _worker_dict(worker: Any) -> dict[str, Any]:
    return {
        "id": worker.id,
        "capabilities": sorted(worker.capabilities),
        "capacity": worker.capacity,
        "active": sorted(worker.active),
        "available": worker.available,
        "accepted": worker.accepted,
        "completed": worker.completed,
        "failed": worker.failed,
        "renewals": worker.renewals,
        "heartbeats": worker.heartbeats,
        "last_seen": worker.last_seen,
    }


@router.get("/status")
def swarm_status(runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    return asdict(runtime.snapshot())


@router.get("/workers")
def list_workers(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    workers = runtime.workers()
    page = workers[offset : offset + limit]
    return {"workers": [_worker_dict(worker) for worker in page], "total": len(workers), "offset": offset, "limit": limit}


@router.post("/workers", status_code=status.HTTP_201_CREATED)
def register_worker(body: WorkerRegistration, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        worker = runtime.register_worker(body.worker_id, capabilities=body.capabilities, capacity=body.capacity)
    except AdmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _worker_dict(worker)


@router.get("/workers/{worker_id}")
def get_worker(worker_id: str, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    worker = runtime.worker(worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="worker not found")
    return _worker_dict(worker)


@router.post("/workers/{worker_id}/heartbeat")
def heartbeat(worker_id: str, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return _worker_dict(runtime.heartbeat(worker_id))
    except LeaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/workers/{worker_id}")
def unregister_worker(worker_id: str, requeue: bool = True, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    existed = runtime.worker(worker_id) is not None
    released = runtime.unregister_worker(worker_id, requeue=requeue)
    if not existed:
        raise HTTPException(status_code=404, detail="worker not found")
    return {"worker_id": worker_id, "released": released, "requeued": requeue}


@router.get("/tasks")
def list_tasks(
    state: Annotated[TaskState | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    tasks = runtime.tasks()
    if state is not None:
        tasks = tuple(task for task in tasks if task.state is state)
    page = tasks[offset : offset + limit]
    return {"tasks": [_task_dict(task) for task in page], "total": len(tasks), "offset": offset, "limit": limit}


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def submit_task(body: TaskSubmission, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        task = runtime.submit(SwarmTask(id=body.task_id, payload=body.payload, priority=body.priority, max_attempts=body.max_attempts, required_capabilities=frozenset(body.required_capabilities)))
    except AdmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _task_dict(task)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    task = runtime.task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _task_dict(task)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, body: CancelRequest, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return _task_dict(runtime.cancel(task_id, reason=body.reason))
    except AdmissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/revive")
def revive_task(task_id: str, body: ReviveRequest, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return _task_dict(runtime.revive(task_id, reset_attempts=body.reset_attempts))
    except AdmissionError as exc:
        if "unknown task" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workers/{worker_id}/lease")
def lease_tasks(
    worker_id: str,
    limit: Annotated[int | None, Query(ge=0, le=1000)] = None,
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        tasks = runtime.lease(worker_id, limit=limit)
    except LeaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"worker_id": worker_id, "tasks": [_task_dict(task) for task in tasks]}


@router.post("/workers/{worker_id}/tasks/{task_id}/renew")
def renew_task(
    worker_id: str,
    task_id: str,
    seconds: Annotated[float | None, Query(gt=0, le=86_400)] = None,
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        return _task_dict(runtime.renew(worker_id, task_id, seconds=seconds))
    except LeaseError as exc:
        code = 404 if "unknown worker" in str(exc) else 409
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/workers/{worker_id}/tasks/{task_id}/success")
def complete_task(worker_id: str, task_id: str, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return _task_dict(runtime.succeed(worker_id, task_id))
    except LeaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workers/{worker_id}/tasks/{task_id}/failure")
def fail_task(worker_id: str, task_id: str, body: FailureReport, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return _task_dict(runtime.fail(worker_id, task_id, body.error))
    except LeaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/reap")
def reap_expired(runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    expired = runtime.reap_expired()
    return {"expired": expired, "snapshot": asdict(runtime.snapshot())}


@router.get("/dead")
def dead_letters(
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    tasks = tuple(runtime.dead())
    return {"tasks": [_task_dict(task) for task in tasks[:limit]], "total": len(tasks), "limit": limit}


@router.get("/state")
def export_state(runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    return runtime.export_state()


@router.post("/state/restore")
def restore_state(body: RestoreRequest) -> dict[str, Any]:
    try:
        runtime = HardenedSwarmRuntime.from_state(body.state, requeue_leased=body.requeue_leased)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid swarm state: {exc}") from exc
    _replace_runtime(runtime)
    return {"restored": True, "snapshot": asdict(runtime.snapshot())}


@router.get("/events")
def events(
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    items = runtime.events()[-limit:]
    return {"events": [{"timestamp": timestamp, "kind": kind, "subject": subject} for timestamp, kind, subject in items]}
