"""Unified bounded submission and dispatch broker for production swarm execution."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from skeleton.agents.swarm_control import SwarmControlPlane
from skeleton.agents.swarm_dedupe import CompletionCache
from skeleton.agents.swarm_exact_lease import lease_exact
from skeleton.agents.swarm_runtime import LeaseError, SwarmRuntime, SwarmTask
from skeleton.agents.swarm_supervisor import SwarmSupervisor


@dataclass(frozen=True, slots=True)
class BrokerResult:
    task_id: str
    submitted: bool
    duplicate: bool
    worker_id: str | None
    leased: bool
    reason: str


@dataclass(frozen=True, slots=True)
class CompletionResult:
    task: SwarmTask
    duplicate: bool


class SwarmBroker:
    def __init__(
        self,
        runtime: SwarmRuntime,
        *,
        control: SwarmControlPlane | None = None,
        supervisor: SwarmSupervisor | None = None,
        completions: CompletionCache | None = None,
    ) -> None:
        self.runtime = runtime
        self.control = control or SwarmControlPlane(runtime)
        self.supervisor = supervisor or SwarmSupervisor()
        self.completions = completions or CompletionCache()
        self._completion_lock = RLock()

    def submit_and_dispatch(self, task: SwarmTask, *, idempotency_key: str | None = None) -> BrokerResult:
        result = self.control.submit(task, idempotency_key=idempotency_key)
        resident = result.task
        if result.duplicate and resident.state.value != "queued":
            return BrokerResult(
                resident.id,
                True,
                True,
                resident.leased_to,
                resident.state.value == "leased",
                f"idempotent resident task is {resident.state.value}",
            )
        decision = self.supervisor.dispatch(self.runtime, resident)
        if not decision.accepted or decision.worker_id is None:
            return BrokerResult(resident.id, True, result.duplicate, None, False, decision.reason)
        try:
            lease_exact(self.runtime, decision.worker_id, resident.id)
        except LeaseError as exc:
            return BrokerResult(resident.id, True, result.duplicate, decision.worker_id, False, str(exc))
        return BrokerResult(resident.id, True, result.duplicate, decision.worker_id, True, "submitted and leased")

    def record_success(self, worker_id: str, task_id: str, *, completion_token: str | None = None) -> CompletionResult:
        if completion_token is None:
            task = self.runtime.succeed(worker_id, task_id)
            self.supervisor.record_success(worker_id)
            return CompletionResult(task, False)
        with self._completion_lock:
            if self.completions.contains(task_id, completion_token):
                resident = self.runtime.task(task_id)
                if resident is None:
                    raise LeaseError(f"unknown task: {task_id}")
                return CompletionResult(resident, True)
            task = self.runtime.succeed(worker_id, task_id)
            self.completions.record(task_id, completion_token)
            self.supervisor.record_success(worker_id)
            return CompletionResult(task, False)

    def record_failure(
        self,
        worker_id: str,
        task_id: str,
        error: str,
        *,
        completion_token: str | None = None,
    ) -> CompletionResult:
        if completion_token is None:
            task = self.runtime.fail(worker_id, task_id, error)
            self.supervisor.record_failure(worker_id)
            return CompletionResult(task, False)
        with self._completion_lock:
            if self.completions.contains(task_id, completion_token):
                resident = self.runtime.task(task_id)
                if resident is None:
                    raise LeaseError(f"unknown task: {task_id}")
                return CompletionResult(resident, True)
            task = self.runtime.fail(worker_id, task_id, error)
            self.completions.record(task_id, completion_token)
            self.supervisor.record_failure(worker_id)
            return CompletionResult(task, False)
