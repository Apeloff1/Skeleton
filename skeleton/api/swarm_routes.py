"""HTTP control plane for the bounded in-process swarm runtime."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from skeleton.agents.swarm_runtime import AdmissionError, LeaseError, SwarmRuntime, SwarmTask

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


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state

    state = get_state()
    runtime = getattr(state, "swarm", None)
    if runtime is None:
        runtime = SwarmRuntime()
        state.swarm = runtime
    return runtime


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
        "last_seen": worker.last_seen,
    }


@router.get("/status")
def swarm_status(runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    return asdict(runtime.snapshot())


@router.post("/workers", status_code=status.HTTP_201_CREATED)
def register_worker(body: WorkerRegistration, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    if runtime.worker(body.worker_id) is not None:
        raise HTTPException(status_code=409, detail="worker already registered")
    try:
        worker = runtime.register_worker(
            body.worker_id,
            capabilities=body.capabilities,
            capacity=body.capacity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _worker_dict(worker)


@router.get("/workers/{worker_id}")
def get_worker(worker_id: str, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    worker = runtime.worker(worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="worker not found")
    return _worker_dict(worker)


@router.delete("/workers/{worker_id}")
def unregister_worker(
    worker_id: str,
    requeue: bool = Query(default=True),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    existed = runtime.worker(worker_id) is not None
    released = runtime.unregister_worker(worker_id, requeue=requeue)
    if not existed:
        raise HTTPException(status_code=404, detail="worker not found")
    return {"worker_id": worker_id, "released": released, "requeued": requeue}


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def submit_task(body: TaskSubmission, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        task = runtime.submit(
            SwarmTask(
                id=body.task_id,
                payload=body.payload,
                priority=body.priority,
                max_attempts=body.max_attempts,
                required_capabilities=frozenset(body.required_capabilities),
            )
        )
    except AdmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _task_dict(task)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    task = runtime.task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _task_dict(task)


@router.post("/workers/{worker_id}/lease")
def lease_tasks(
    worker_id: str,
    limit: int | None = Query(default=None, ge=0, le=10_000),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        tasks = runtime.lease(worker_id, limit=limit)
    except LeaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"worker_id": worker_id, "tasks": [_task_dict(task) for task in tasks]}


@router.post("/workers/{worker_id}/tasks/{task_id}/success")
def complete_task(worker_id: str, task_id: str, runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return _task_dict(runtime.succeed(worker_id, task_id))
    except LeaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workers/{worker_id}/tasks/{task_id}/failure")
def fail_task(
    worker_id: str,
    task_id: str,
    body: FailureReport,
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        return _task_dict(runtime.fail(worker_id, task_id, body.error))
    except LeaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/reap")
def reap_expired(runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    expired = runtime.reap_expired()
    return {"expired": expired, "snapshot": asdict(runtime.snapshot())}


@router.get("/events")
def events(
    limit: int = Query(default=100, ge=1, le=10_000),
    runtime: SwarmRuntime = Depends(_runtime),
) -> dict[str, Any]:
    items = runtime.events()[-limit:]
    return {
        "events": [
            {"timestamp": timestamp, "kind": kind, "subject": subject}
            for timestamp, kind, subject in items
        ]
    }
