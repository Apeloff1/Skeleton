"""Durable, quota-convergent supervisor authority for the agent swarm runtime.

This module composes existing bounded swarm primitives instead of introducing a
second scheduler. The supervisor owns four boundaries that were previously
separate:

* SQLite run ownership fences which supervisor process may commit state.
* SwarmRecoveryManager plus SwarmDurableBridge provide restart-safe snapshots.
* QuotaLedger is reconciled from canonical runtime state before every commit.
* Runtime mutations use copy-on-write and become authoritative only after the
  durable checkpoint succeeds.

The result is deliberately synchronous. There are no hidden threads, timers,
network clients, or model calls here; a host explicitly drives every mutation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import monotonic
from typing import Callable, TypeVar

from skeleton.automation.agents.swarm_durable import (
    DurableSwarmCapture,
    SwarmDurableBridge,
)
from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.automation.agents.swarm_quota import Quota, QuotaLedger, Usage
from skeleton.automation.agents.swarm_recovery import RecoveryStatus, SwarmRecoveryManager
from skeleton.automation.agents.swarm_runtime import (
    RuntimeSnapshot,
    SwarmRuntime,
    SwarmTask,
    WorkerState,
)
from skeleton.automation.agents.swarm_supervisor import DispatchDecision, SwarmSupervisor
from skeleton.state import RunNotFound, RunRecord, SQLiteRunStore, StateConflict

_T = TypeVar("_T")


class AgentSupervisorError(RuntimeError):
    """Base error for the durable agent-supervisor control plane."""


class AgentResourceAccountingError(AgentSupervisorError):
    """Raised when runtime resource usage cannot be measured safely."""


class AgentResourceAccountingDrift(AgentResourceAccountingError):
    """Raised when another writer changed the supervisor's quota scope."""


@dataclass(frozen=True, slots=True)
class AgentResourceMeasurement:
    """Canonical resource measurement derived from one runtime image."""

    queued: int
    leased: int
    payload_bytes: int
    resident_tasks: int

    @property
    def usage(self) -> Usage:
        return Usage(
            queued=self.queued,
            leased=self.leased,
            payload_bytes=self.payload_bytes,
        )


@dataclass(frozen=True, slots=True)
class AgentSupervisorCommit:
    """Receipt for one resource-qualified durable runtime commit."""

    swarm_sequence: int
    checkpoint_id: str
    checkpoint_revision: int
    resource_usage: Usage
    resident_tasks: int


@dataclass(frozen=True, slots=True)
class AgentSupervisorStatus:
    """Read-only status across durable ownership, runtime and recovery."""

    run: RunRecord
    resources: Usage
    runtime: RuntimeSnapshot
    recovery: RecoveryStatus


def measure_agent_resources(runtime: SwarmRuntime) -> AgentResourceMeasurement:
    """Measure quota-bearing state without trusting incremental counters.

    Queue and lease counts come from the runtime state-count invariant.
    Payload bytes are recomputed from every resident task because terminal task
    payloads still consume resident state until compaction. JSON encoding is
    canonical and rejects NaN/Infinity and non-serializable objects.
    """

    if not isinstance(runtime, SwarmRuntime):
        raise TypeError("runtime must be a SwarmRuntime")
    snapshot = runtime.snapshot()
    payload_bytes = 0
    tasks = runtime.tasks()
    for task in tasks:
        try:
            encoded = json.dumps(
                dict(task.payload),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise AgentResourceAccountingError(
                f"task {task.id!r} payload is not finite canonical JSON"
            ) from exc
        payload_bytes += len(encoded)
    return AgentResourceMeasurement(
        queued=snapshot.queued,
        leased=snapshot.leased,
        payload_bytes=payload_bytes,
        resident_tasks=len(tasks),
    )


class AgentResourceAccountant:
    """Converge one quota scope to measured runtime truth.

    The ledger is intentionally not treated as the source of runtime truth.
    Each reconciliation derives desired usage from the runtime, compares the
    ledger against the last supervisor-observed value, then applies only the
    exact delta. Unexpected external writes fail closed as accounting drift.
    """

    def __init__(self, ledger: QuotaLedger, scope: str) -> None:
        if not isinstance(ledger, QuotaLedger):
            raise TypeError("ledger must be a QuotaLedger")
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("resource scope must not be empty")
        self.ledger = ledger
        self.scope = scope.strip()
        self._accounted = ledger.usage(self.scope)

    @property
    def accounted(self) -> Usage:
        return self._accounted

    def _apply(self, target: Usage) -> Usage:
        observed = self.ledger.usage(self.scope)
        if observed != self._accounted:
            raise AgentResourceAccountingDrift(
                "quota scope changed outside durable agent supervisor"
            )
        updated = self.ledger.reserve(
            self.scope,
            queued=target.queued - observed.queued,
            leased=target.leased - observed.leased,
            payload_bytes=target.payload_bytes - observed.payload_bytes,
        )
        self._accounted = updated
        return updated

    def reconcile(self, runtime: SwarmRuntime) -> AgentResourceMeasurement:
        measured = measure_agent_resources(runtime)
        self._apply(measured.usage)
        return measured

    def restore(self, usage: Usage) -> Usage:
        if not isinstance(usage, Usage):
            raise TypeError("usage must be Usage")
        return self._apply(usage)


class DurableAgentSupervisor:
    """Authoritative durable mutation gateway for a bounded swarm runtime.

    Callers should mutate through this object rather than retaining and
    modifying the runtime directly. Every mutating operation clones the current
    runtime, applies the change to the candidate, reconciles quotas, persists a
    recovery checkpoint under a live SQLite ownership lease, and only then
    swaps the candidate into the authoritative runtime slot.
    """

    def __init__(
        self,
        *,
        store: SQLiteRunStore,
        run_id: str,
        supervisor_id: str,
        runtime: SwarmRuntime,
        recovery: SwarmRecoveryManager,
        ledger: QuotaLedger,
        scope: str,
        lease_seconds: float,
        runtime_clock: Callable[[], float],
        policy: SwarmSupervisor | None = None,
    ) -> None:
        if not isinstance(store, SQLiteRunStore):
            raise TypeError("store must be SQLiteRunStore")
        if not isinstance(runtime, SwarmRuntime):
            raise TypeError("runtime must be SwarmRuntime")
        if not isinstance(recovery, SwarmRecoveryManager):
            raise TypeError("recovery must be SwarmRecoveryManager")
        if isinstance(lease_seconds, bool) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if not callable(runtime_clock):
            raise TypeError("runtime_clock must be callable")
        self.store = store
        self.run_id = run_id
        self.supervisor_id = supervisor_id
        self.lease_seconds = float(lease_seconds)
        self._runtime_clock = runtime_clock
        self.recovery = recovery
        self.bridge = SwarmDurableBridge(store)
        self.ledger = ledger
        self.accountant = AgentResourceAccountant(ledger, scope)
        self.policy = policy or SwarmSupervisor()
        self._runtime = runtime
        self._last_commit: AgentSupervisorCommit | None = None

    @classmethod
    def open(
        cls,
        store: SQLiteRunStore,
        run_id: str,
        supervisor_id: str,
        *,
        quota: Quota | None = None,
        ledger: QuotaLedger | None = None,
        resource_scope: str | None = None,
        lease_seconds: float = 60.0,
        max_checkpoints: int = 8,
        runtime_clock: Callable[[], float] = monotonic,
        policy: SwarmSupervisor | None = None,
    ) -> "DurableAgentSupervisor":
        """Claim durable ownership and recover the latest verified runtime.

        A missing run is created exactly once. Concurrent creation races are
        resolved by the run store; a live owner blocks a second supervisor.
        Persisted task leases are requeued by the recovery manager before the
        recovered image is recommitted under the new supervisor lease.
        """

        if not isinstance(store, SQLiteRunStore):
            raise TypeError("store must be SQLiteRunStore")
        if isinstance(max_checkpoints, bool) or not isinstance(max_checkpoints, int):
            raise ValueError("max_checkpoints must be a positive integer")
        if max_checkpoints < 1:
            raise ValueError("max_checkpoints must be a positive integer")
        try:
            store.get_run(run_id)
        except RunNotFound:
            try:
                store.create_run(
                    run_id,
                    {
                        "kind": "durable-agent-supervisor",
                        "resource_scope": resource_scope or f"agent-runtime:{run_id}",
                    },
                )
            except StateConflict:
                pass
        store.claim_run(
            run_id,
            supervisor_id,
            lease_seconds=lease_seconds,
        )

        bridge = SwarmDurableBridge(store)
        loaded = bridge.load(run_id)
        if loaded is None:
            recovery = SwarmRecoveryManager(max_checkpoints=max_checkpoints)
            runtime: SwarmRuntime = HardenedSwarmRuntime(clock=runtime_clock)
        else:
            recovery = loaded.manager
            restored = loaded.restore_runtime()
            if restored is None:
                runtime = HardenedSwarmRuntime(clock=runtime_clock)
            else:
                runtime = type(restored).from_state(
                    restored.export_state(),
                    clock=runtime_clock,
                    requeue_leased=False,
                )

        quota_ledger = ledger or QuotaLedger()
        scope = resource_scope or f"agent-runtime:{run_id}"
        if quota is not None:
            quota_ledger.configure(scope, quota)

        supervisor = cls(
            store=store,
            run_id=run_id,
            supervisor_id=supervisor_id,
            runtime=runtime,
            recovery=recovery,
            ledger=quota_ledger,
            scope=scope,
            lease_seconds=lease_seconds,
            runtime_clock=runtime_clock,
            policy=policy,
        )
        supervisor._commit(runtime, renew_outer_lease=False)
        return supervisor

    @property
    def runtime(self) -> SwarmRuntime:
        return self._runtime

    @property
    def resource_scope(self) -> str:
        return self.accountant.scope

    @property
    def last_commit(self) -> AgentSupervisorCommit | None:
        return self._last_commit

    def heartbeat(self) -> RunRecord:
        """Renew the outer supervisor ownership fence."""

        return self.store.heartbeat(
            self.run_id,
            self.supervisor_id,
            lease_seconds=self.lease_seconds,
        )

    def dispatch(self, task: SwarmTask) -> DispatchDecision:
        """Evaluate load/circuit/quarantine policy against authoritative state."""

        return self.policy.dispatch(self._runtime, task)

    def status(self) -> AgentSupervisorStatus:
        return AgentSupervisorStatus(
            run=self.store.get_run(self.run_id),
            resources=self.accountant.accounted,
            runtime=self._runtime.snapshot(),
            recovery=self.recovery.status(),
        )

    def checkpoint(self) -> AgentSupervisorCommit:
        """Persist an explicit no-semantic-change checkpoint."""

        candidate = self._clone_runtime()
        return self._commit(candidate)

    def _clone_runtime(self) -> SwarmRuntime:
        return type(self._runtime).from_state(
            self._runtime.export_state(),
            clock=self._runtime_clock,
            requeue_leased=False,
        )

    def _commit(
        self,
        candidate: SwarmRuntime,
        *,
        renew_outer_lease: bool = True,
    ) -> AgentSupervisorCommit:
        if renew_outer_lease:
            self.heartbeat()
        previous_usage = self.accountant.accounted
        measurement = self.accountant.reconcile(candidate)
        try:
            capture: DurableSwarmCapture = self.bridge.capture(
                self.run_id,
                self.supervisor_id,
                self.recovery,
                candidate,
            )
        except Exception:
            self.accountant.restore(previous_usage)
            raise
        commit = AgentSupervisorCommit(
            swarm_sequence=capture.swarm_sequence,
            checkpoint_id=capture.checkpoint.checkpoint_id,
            checkpoint_revision=capture.checkpoint.revision,
            resource_usage=measurement.usage,
            resident_tasks=measurement.resident_tasks,
        )
        self._runtime = candidate
        self._last_commit = commit
        return commit

    def _mutate(self, mutation: Callable[[SwarmRuntime], _T]) -> _T:
        candidate = self._clone_runtime()
        result = mutation(candidate)
        self._commit(candidate)
        return result

    def register_worker(
        self,
        worker_id: str,
        *,
        capabilities: tuple[str, ...] | list[str] | frozenset[str] = (),
        capacity: int = 1,
    ) -> WorkerState:
        return self._mutate(
            lambda runtime: runtime.register_worker(
                worker_id,
                capabilities=capabilities,
                capacity=capacity,
            )
        )

    def unregister_worker(self, worker_id: str, *, requeue: bool = True) -> int:
        return self._mutate(
            lambda runtime: runtime.unregister_worker(worker_id, requeue=requeue)
        )

    def worker_heartbeat(self, worker_id: str) -> WorkerState:
        return self._mutate(lambda runtime: runtime.heartbeat(worker_id))

    def submit(self, task: SwarmTask) -> SwarmTask:
        return self._mutate(lambda runtime: runtime.submit(task))

    def lease(self, worker_id: str, *, limit: int | None = None) -> list[SwarmTask]:
        return self._mutate(lambda runtime: runtime.lease(worker_id, limit=limit))

    def renew(
        self,
        worker_id: str,
        task_id: str,
        *,
        seconds: float | None = None,
    ) -> SwarmTask:
        return self._mutate(
            lambda runtime: runtime.renew(worker_id, task_id, seconds=seconds)
        )

    def succeed(self, worker_id: str, task_id: str) -> SwarmTask:
        return self._mutate(lambda runtime: runtime.succeed(worker_id, task_id))

    def fail(self, worker_id: str, task_id: str, error: str) -> SwarmTask:
        return self._mutate(lambda runtime: runtime.fail(worker_id, task_id, error))

    def cancel(self, task_id: str, *, reason: str = "cancelled") -> SwarmTask:
        return self._mutate(lambda runtime: runtime.cancel(task_id, reason=reason))

    def revive(self, task_id: str, *, reset_attempts: bool = False) -> SwarmTask:
        return self._mutate(
            lambda runtime: runtime.revive(task_id, reset_attempts=reset_attempts)
        )

    def reap_expired(self) -> int:
        return self._mutate(lambda runtime: runtime.reap_expired())


__all__ = [
    "AgentResourceAccountant",
    "AgentResourceAccountingDrift",
    "AgentResourceAccountingError",
    "AgentResourceMeasurement",
    "AgentSupervisorCommit",
    "AgentSupervisorError",
    "AgentSupervisorStatus",
    "DurableAgentSupervisor",
    "measure_agent_resources",
]
