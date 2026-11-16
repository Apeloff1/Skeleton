"""Durable persistence bridge for the existing swarm recovery manager.

This module does not implement another scheduler or checkpoint format. It stores
``SwarmRecoveryManager``'s already-versioned, checksummed archive inside a
provider-neutral durable run store so swarm state survives process restarts
while the existing recovery manager remains the canonical swarm serializer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from skeleton.automation.agents.swarm_recovery import (
    SUPPORTED_RECOVERY_ARCHIVE_VERSIONS, SwarmRecoveryManager,
)
from skeleton.automation.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState
from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
from skeleton.state import CheckpointRecord, ResumeState


@runtime_checkable
class DurableCheckpointStore(Protocol):
    """Minimal durable-store surface required by the swarm recovery bridge."""

    def checkpoint(
        self,
        run_id: str,
        state: Any,
        *,
        worker_id: str,
        after_step_id: str | None = None,
        state_version: int = 1,
    ) -> CheckpointRecord: ...

    def resume_state(self, run_id: str) -> ResumeState: ...


class DurableSwarmError(RuntimeError):
    """Raised when durable swarm state violates the bridge contract."""


@dataclass(frozen=True, slots=True)
class DurableSwarmCapture:
    """One swarm checkpoint captured and committed to durable storage."""

    swarm_sequence: int
    checkpoint: CheckpointRecord


@dataclass(frozen=True, slots=True)
class DurableSwarmRecovery:
    """Verified swarm recovery archive plus its outer run replay state."""

    manager: SwarmRecoveryManager
    checkpoint: CheckpointRecord
    resume: ResumeState

    def restore_runtime(self):
        """Restore legacy leases or hold fenced attempts for reconciliation."""
        return self.manager.restore_latest()


class SwarmDurableBridge:
    """Persist canonical swarm recovery archives through a durable checkpoint store."""

    def __init__(self, store: DurableCheckpointStore) -> None:
        if not isinstance(store, DurableCheckpointStore):
            raise TypeError("store must implement the durable checkpoint-store contract")
        self.store = store

    def persist(
        self,
        run_id: str,
        worker_id: str,
        manager: SwarmRecoveryManager,
        *,
        after_step_id: str | None = None,
    ) -> CheckpointRecord:
        """Persist the manager's verified bounded archive as one run checkpoint."""
        if not isinstance(manager, SwarmRecoveryManager):
            raise TypeError("manager must be a SwarmRecoveryManager")
        archive = manager.export_archive()
        version = archive.get("version")
        if type(version) is not int or version not in SUPPORTED_RECOVERY_ARCHIVE_VERSIONS:
            raise DurableSwarmError(
                "swarm recovery archive version disagrees with the runtime contract"
            )
        return self.store.checkpoint(
            run_id,
            archive,
            worker_id=worker_id,
            after_step_id=after_step_id,
            state_version=version,
        )

    def capture(
        self,
        run_id: str,
        worker_id: str,
        manager: SwarmRecoveryManager,
        runtime: SwarmRuntime,
        *,
        tenant_broker: TenantSwarmBroker | None = None,
        after_step_id: str | None = None,
    ) -> DurableSwarmCapture:
        """Capture swarm state and durably commit it as one logical operation.

        If durable persistence fails, the just-created in-memory swarm/tenant
        checkpoint is discarded. Older retained recovery history is untouched.
        """
        if not isinstance(manager, SwarmRecoveryManager):
            raise TypeError("manager must be a SwarmRecoveryManager")
        if not isinstance(runtime, SwarmRuntime):
            raise TypeError("runtime must be a SwarmRuntime")
        if tenant_broker is not None and not isinstance(tenant_broker, TenantSwarmBroker):
            raise TypeError("tenant_broker must be a TenantSwarmBroker or None")

        # Keep old retained snapshots even when an append evicts a ring entry.
        # Hold the owner locks across storage publication, not model execution.
        from contextlib import nullcontext
        tenant_lock = tenant_broker._lock if tenant_broker is not None else nullcontext()
        runtime_lock = getattr(runtime, "_lock", None) or nullcontext()
        with tenant_lock, runtime_lock, manager._lock:
            prior_runtime = manager.store.history()
            prior_tenants = manager.tenant_store.history()
            sequence = manager.checkpoint(runtime, tenant_broker)
            try:
                checkpoint = self.persist(
                    run_id, worker_id, manager, after_step_id=after_step_id,
                )
            except Exception:
                with manager.store._lock, manager.tenant_store._lock:
                    manager.store._items.clear()
                    manager.store._items.extend(prior_runtime)
                    manager.tenant_store._items.clear()
                    manager.tenant_store._items.extend(prior_tenants)
                raise
            return DurableSwarmCapture(sequence, checkpoint)

    def lease_and_capture_verified(self, run_id: str, worker_id: str,
                                   manager: SwarmRecoveryManager,
                                   tenant_broker: TenantSwarmBroker,
                                   candidates: tuple, *, now_ms: int
                                   ) -> tuple[str, SwarmTask, DurableSwarmCapture] | None:
        """Trusted owner boundary: commit the lease before returning its token.

        The existing durable run store must already own the exclusive run
        writer lease. No independent distributed writer election is supplied.
        If storage or its acknowledgement is uncertain, retire this broker
        generation and retain the task's worker and tenant custody; never
        publish the lease to a worker or automatically replay the task.
        """
        if not tenant_broker.verified_mode:
            raise DurableSwarmError("verified tenant custody required")
        runtime = tenant_broker.broker.runtime
        with tenant_broker._lock, runtime._lock, manager._lock:
            tenant_broker._assert_verified()
            selected = tenant_broker.lease_ranked_verified(candidates, now_ms=now_ms)
            if selected is None:
                return None
            tenant, task = selected
            try:
                capture = self.capture(run_id, worker_id, manager, runtime,
                                       tenant_broker=tenant_broker)
                latest = self.store.resume_state(run_id).checkpoint
                if (latest is None or latest.state_version != capture.checkpoint.state_version
                        or manager._json_bytes(latest.state) != manager._json_bytes(capture.checkpoint.state)
                        or manager._json_bytes(latest.state) != manager._json_bytes(manager.export_archive())):
                    raise DurableSwarmError("durable attempt publication readback mismatch")
            except Exception as exc:
                resident = runtime.task(task.id)
                if resident is not None and resident.state is TaskState.LEASED:
                    runtime._hold_uncertain(resident, reason="durable dispatch acknowledgement uncertain")
                tenant_broker.retire()
                raise DurableSwarmError("verified dispatch stopped; reconcile durable custody") from exc
            return tenant, task, capture

    def _capture_checked(self, run_id: str, worker_id: str, manager: SwarmRecoveryManager,
                         broker: TenantSwarmBroker) -> DurableSwarmCapture:
        capture = self.capture(run_id, worker_id, manager, broker.broker.runtime,
                               tenant_broker=broker)
        latest = self.store.resume_state(run_id).checkpoint
        if (latest is None or latest.state_version != capture.checkpoint.state_version
                or manager._json_bytes(latest.state) != manager._json_bytes(capture.checkpoint.state)
                or manager._json_bytes(latest.state) != manager._json_bytes(manager.export_archive())):
            raise DurableSwarmError("durable publication readback mismatch")
        return capture

    def submit_unique_verified(self, run_id: str, worker_id: str,
                               manager: SwarmRecoveryManager, broker: TenantSwarmBroker,
                               tenant: str, task: SwarmTask) -> DurableSwarmCapture | None:
        """Persist an admitted unique job before returning acknowledgement.

        The existing tenant task identity is the idempotency key. Replay may
        checkpoint the same resident again, but cannot create a second job.
        The host holds the exclusive run writer and must restore the latest
        archive after any ambiguous acknowledgement. Direct bypass is outside
        the verified owner contract.
        """
        runtime = broker.broker.runtime
        with broker._lock, runtime._lock, manager._lock:
            broker._assert_verified()
            try:
                result = broker.submit_verified_queued(tenant, task)
                if not result.admitted:
                    return None
                return self._capture_checked(run_id, worker_id, manager, broker)
            except Exception as exc:
                # Even an exception on submission may have occurred after a
                # mutation. Never continue dispatch from an ambiguous owner.
                broker.retire()
                raise DurableSwarmError("unique job publication stopped; restore durable custody") from exc

    def reconcile_and_enqueue_verified(self, run_id: str, worker_id: str,
                                       manager: SwarmRecoveryManager, broker: TenantSwarmBroker,
                                       tenant: str, parent_id: str, parent_worker: str, *,
                                       lease_token: str, evidence_sha256: str,
                                       followups: tuple[SwarmTask, ...]) -> DurableSwarmCapture:
        """Commit an uncertain parent's verified success and queued children together.

        Child admission happens while the parent still holds its dependency
        barrier. The existing checkpoint store publishes one complete archive
        after reconciliation. If any mutation or write is ambiguous, retire
        the generation without returning success; recovery uses the actual
        durable archive, never the partially mutated in-memory generation.
        This is atomic archive visibility, not a transaction with external
        effects or an independent outbox service.
        """
        from hashlib import sha256
        import json

        if (type(followups) is not tuple or not 1 <= len(followups) <= 64
                or any(not isinstance(t, SwarmTask) for t in followups)):
            raise DurableSwarmError("invalid follow-up batch")
        if len({t.id for t in followups}) != len(followups):
            raise DurableSwarmError("duplicate follow-up identity")
        manifest = []
        for task in followups:
            if (task.dependencies != (parent_id,) or task.id == parent_id
                    or task.state is not TaskState.QUEUED or task.attempts or task.effect_uncertain
                    or task.lease_token is not None or task.leased_to is not None
                    or task.lease_deadline is not None or task.reconciliation_sha256 is not None):
                raise DurableSwarmError("follow-up must be fresh and depend only on parent")
            manifest.append([task.id, dict(task.payload), task.priority, task.max_attempts,
                             sorted(task.required_capabilities), task.dependencies])
        encoded = json.dumps([run_id, tenant, parent_id, manifest], sort_keys=True,
                             separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
        if len(encoded) > 1024 * 1024:
            raise DurableSwarmError("follow-up manifest exceeds bound")
        pin = sha256(encoded).hexdigest()
        runtime = broker.broker.runtime
        with broker._lock, broker.broker._completion_lock, runtime._lock, manager._lock:
            broker._assert_verified()
            parent = broker._verified_resident(tenant, parent_id)
            if not parent.effect_uncertain or parent.leased_to != parent_worker or parent.lease_token != lease_token:
                raise DurableSwarmError("parent uncertain attempt does not match")
            # Trusted host must independently authorize the exact continuation
            # manifest in addition to the parent's actual outcome evidence.
            broker.broker._verified(parent_worker, parent_id, lease_token,
                                    "enqueue:" + pin, evidence_sha256)
            broker.broker._verified(parent_worker, parent_id, lease_token,
                                    "reconcile:committed", evidence_sha256)
            for task in followups:
                if (broker.tenant_for(task.id) is not None or runtime.task(task.id) is not None):
                    raise DurableSwarmError("follow-up identity already resident")
            try:
                for task in followups:
                    decision = broker.submit_verified_queued(tenant, task)
                    if not decision.admitted or decision.duplicate:
                        raise DurableSwarmError("follow-up admission refused")
                broker.reconcile_verified(tenant, parent_worker, parent_id,
                                          lease_token=lease_token, outcome="committed",
                                          evidence_sha256=evidence_sha256)
                return self._capture_checked(run_id, worker_id, manager, broker)
            except Exception as exc:
                broker.retire()
                raise DurableSwarmError("completion and enqueue stopped; restore durable custody") from exc

    def load(self, run_id: str) -> DurableSwarmRecovery | None:
        """Load and verify the latest durable swarm archive for an outer run."""
        resume = self.store.resume_state(run_id)
        checkpoint = resume.checkpoint
        if checkpoint is None:
            return None
        if checkpoint.state_version not in SUPPORTED_RECOVERY_ARCHIVE_VERSIONS:
            raise DurableSwarmError(
                "unsupported durable swarm checkpoint state version: "
                f"{checkpoint.state_version}"
            )
        if not isinstance(checkpoint.state, dict):
            raise DurableSwarmError("durable swarm checkpoint must contain an object")
        archive_version = checkpoint.state.get("version")
        if archive_version != checkpoint.state_version:
            raise DurableSwarmError("durable checkpoint envelope/archive version mismatch")
        try:
            manager = SwarmRecoveryManager.from_archive(checkpoint.state)
        except (TypeError, ValueError) as exc:
            raise DurableSwarmError("invalid durable swarm recovery archive") from exc
        return DurableSwarmRecovery(
            manager=manager,
            checkpoint=checkpoint,
            resume=resume,
        )

    def restore_runtime(self, run_id: str):
        """Restore the latest swarm runtime, or ``None`` when no archive exists."""
        recovery = self.load(run_id)
        return None if recovery is None else recovery.restore_runtime()
