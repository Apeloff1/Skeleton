"""Lease fencing primitives preventing stale completion after retries/reissues."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import ContextManager

from skeleton.automation.agents.swarm_runtime import LeaseError, SwarmRuntime, SwarmTask, TaskState


@dataclass(frozen=True, slots=True)
class LeaseFence:
    task_id: str
    worker_id: str
    attempt: int
    deadline: float | None
    lease_token: str | None = None


def fence_for(task: SwarmTask) -> LeaseFence:
    if task.state is not TaskState.LEASED or task.leased_to is None:
        raise LeaseError(f"task is not leased: {task.id}")
    return LeaseFence(task.id, task.leased_to, task.attempts, task.lease_deadline, task.lease_token)


def _guard(runtime: SwarmRuntime) -> ContextManager[object]:
    lock = getattr(runtime, "_lock", None)
    return lock if lock is not None else nullcontext()


def assert_fence(runtime: SwarmRuntime, fence: LeaseFence) -> SwarmTask:
    task = runtime.task(fence.task_id)
    if task is None or task.state is not TaskState.LEASED:
        raise LeaseError(f"task is not leased: {fence.task_id}")
    if task.leased_to != fence.worker_id:
        raise LeaseError(f"lease owner changed: {fence.task_id}")
    if task.attempts != fence.attempt:
        raise LeaseError(
            f"stale lease attempt for {fence.task_id}: expected {task.attempts}, got {fence.attempt}"
        )
    if runtime.fenced:
        if not fence.lease_token or task.lease_token != fence.lease_token:
            raise LeaseError("stale attempt token")
        if task.lease_deadline is None or runtime._clock() >= task.lease_deadline:
            raise LeaseError("attempt expired")
    return task


def fenced_succeed(runtime: SwarmRuntime, fence: LeaseFence) -> SwarmTask:
    with _guard(runtime):
        assert_fence(runtime, fence)
        if runtime.fenced:
            return runtime.succeed(fence.worker_id, fence.task_id, lease_token=fence.lease_token)
        return runtime.succeed(fence.worker_id, fence.task_id)


def fenced_fail(runtime: SwarmRuntime, fence: LeaseFence, error: str, *,
                confirmed_no_effect: bool = False) -> SwarmTask:
    with _guard(runtime):
        assert_fence(runtime, fence)
        if runtime.fenced:
            return runtime.fail(fence.worker_id, fence.task_id, error,
                                lease_token=fence.lease_token, confirmed_no_effect=confirmed_no_effect)
        return runtime.fail(fence.worker_id, fence.task_id, error)


def fenced_renew(runtime: SwarmRuntime, fence: LeaseFence, *, seconds: float | None = None) -> SwarmTask:
    with _guard(runtime):
        assert_fence(runtime, fence)
        if runtime.fenced:
            return runtime.renew(fence.worker_id, fence.task_id, seconds=seconds, lease_token=fence.lease_token)
        return runtime.renew(fence.worker_id, fence.task_id, seconds=seconds)
