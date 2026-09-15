"""Durable persistence bridge for the existing swarm recovery manager.

This module does not implement another scheduler or checkpoint format. It stores
``SwarmRecoveryManager``'s already-versioned, checksummed archive inside a
provider-neutral durable run store so swarm state survives process restarts
while the existing recovery manager remains the canonical swarm serializer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from skeleton.agents.swarm_recovery import RECOVERY_ARCHIVE_VERSION, SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmRuntime
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker
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
        """Restore the latest retained swarm runtime, requeuing persisted leases."""
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
        if version != RECOVERY_ARCHIVE_VERSION:
            raise DurableSwarmError(
                "swarm recovery archive version disagrees with the runtime contract"
            )
        return self.store.checkpoint(
            run_id,
            archive,
            worker_id=worker_id,
            after_step_id=after_step_id,
            state_version=RECOVERY_ARCHIVE_VERSION,
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

        sequence = manager.checkpoint(runtime, tenant_broker)
        try:
            checkpoint = self.persist(
                run_id,
                worker_id,
                manager,
                after_step_id=after_step_id,
            )
        except Exception:
            manager.store.discard(sequence)
            manager.tenant_store.discard(sequence)
            raise
        return DurableSwarmCapture(sequence, checkpoint)

    def load(self, run_id: str) -> DurableSwarmRecovery | None:
        """Load and verify the latest durable swarm archive for an outer run."""
        resume = self.store.resume_state(run_id)
        checkpoint = resume.checkpoint
        if checkpoint is None:
            return None
        if checkpoint.state_version != RECOVERY_ARCHIVE_VERSION:
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
