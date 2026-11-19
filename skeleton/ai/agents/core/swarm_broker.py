"""Unified bounded submission and dispatch broker for production swarm execution."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
import re
from threading import RLock

from skeleton.automation.agents.swarm_control import SwarmControlPlane
from skeleton.automation.agents.swarm_dedupe import CompletionCache
from skeleton.automation.agents.swarm_exact_lease import lease_exact
from skeleton.automation.agents.swarm_runtime import LeaseError, SwarmRuntime, SwarmTask, TaskState
from skeleton.automation.agents.swarm_supervisor import SwarmSupervisor


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
        verify_worker: Callable[[str, str, str, str, str], bool] | None = None,
    ) -> None:
        if runtime.fenced and (not callable(verify_worker) or getattr(runtime, "_lock", None) is None):
            raise LeaseError("fenced runtime requires a trusted verifier and hardened runtime")
        self._verify_worker = verify_worker
        if control is not None and control.runtime is not runtime:
            raise LeaseError("control plane does not own the broker runtime")
        self.runtime = runtime
        self.control = control or SwarmControlPlane(runtime)
        self.supervisor = supervisor or SwarmSupervisor()
        self.completions = completions or CompletionCache()
        self._completion_lock = RLock()

    def _verified(self, worker_id: str, task_id: str, lease_token: str,
                  action: str, evidence_sha256: str) -> None:
        # The injected host verifier authenticates the worker and validates
        # the referenced immutable evidence. A digest alone proves nothing.
        if not self.runtime.fenced or self._verify_worker is None:
            raise LeaseError("verified dispatch is not configured")
        if type(evidence_sha256) is not str or not re.fullmatch("[0-9a-f]{64}", evidence_sha256):
            raise LeaseError("invalid evidence digest")
        if type(lease_token) is not str or not re.fullmatch("[0-9a-f]{32}", lease_token):
            raise LeaseError("invalid attempt token")
        if self._verify_worker(worker_id, task_id, lease_token, action, evidence_sha256) is not True:
            raise LeaseError("worker or evidence verification refused")

    def submit_queued(self, task: SwarmTask, *, idempotency_key: str | None = None) -> SwarmTask:
        """Admission only; no worker can start before an existing owner permits leasing."""
        return self.control.submit(task, idempotency_key=idempotency_key).task

    def lease_authorized(self, task_id: str) -> SwarmTask | None:
        """Trusted host-only exact dispatch; return the attempt to its authenticated transport."""
        if not self.runtime.fenced:
            raise LeaseError("verified dispatch is not configured")
        with self.runtime._lock:
            resident = self.runtime.task(task_id)
            if resident is None or resident.state is not TaskState.QUEUED:
                return None
            if self.runtime.dispatch_blocked(task_id):
                return None
            decision = self.supervisor.dispatch(self.runtime, resident)
            if not decision.accepted or decision.worker_id is None:
                return None
            return lease_exact(self.runtime, decision.worker_id, task_id)

    def record_verified(self, worker_id: str, task_id: str, *, lease_token: str,
                        outcome: str, evidence_sha256: str) -> CompletionResult:
        """Trusted local boundary. Never replay an ambiguous physical effect."""
        if outcome not in {"success", "no-effect", "uncertain"}:
            raise LeaseError("unsupported worker outcome")
        self._verified(worker_id, task_id, lease_token, outcome, evidence_sha256)
        with self._completion_lock, self.runtime._lock:
            # Recheck the exact attempt after independent verification.
            resident = self.runtime.task(task_id)
            if resident is None or resident.leased_to != worker_id or resident.lease_token != lease_token:
                raise LeaseError("attempt changed")
            if outcome == "success":
                task = self.runtime.succeed(worker_id, task_id, lease_token=lease_token)
                self.supervisor.record_success(worker_id)
            else:
                task = self.runtime.fail(worker_id, task_id, "verified failure", lease_token=lease_token,
                                         confirmed_no_effect=outcome == "no-effect")
                self.supervisor.record_failure(worker_id)
            return CompletionResult(task, False)

    def reconcile_verified(self, worker_id: str, task_id: str, *, lease_token: str,
                           outcome: str, evidence_sha256: str) -> CompletionResult:
        if outcome not in {"committed", "stopped-no-effect", "stopped-terminal"}:
            raise LeaseError("unsupported reconciliation outcome")
        self._verified(worker_id, task_id, lease_token, "reconcile:" + outcome, evidence_sha256)
        with self._completion_lock, self.runtime._lock:
            resident = self.runtime.task(task_id)
            if resident is None or resident.leased_to != worker_id or resident.lease_token != lease_token:
                raise LeaseError("attempt changed")
            return CompletionResult(self.runtime.reconcile_uncertain(
                task_id, lease_token=lease_token, outcome=outcome, evidence_sha256=evidence_sha256,
            ), False)

    def submit_and_dispatch(self, task: SwarmTask, *, idempotency_key: str | None = None) -> BrokerResult:
        if self.runtime.fenced:
            raise LeaseError("fenced work requires the explicit trusted host dispatch boundary")
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
        if self.runtime.fenced:
            raise LeaseError("fenced work requires verified completion")
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
        if self.runtime.fenced:
            raise LeaseError("fenced work requires verified completion")
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
