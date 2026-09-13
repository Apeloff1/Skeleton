"""Checkpoint and failover coordination for swarm runtime recovery."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Mapping

from skeleton.agents.swarm_checkpoint import CheckpointStore
from skeleton.agents.swarm_failover import FailoverCoordinator, ReplicaState
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmRuntime
from skeleton.agents.swarm_tenant_broker import TenantRepairResult, TenantSwarmBroker
from skeleton.agents.swarm_tenant_checkpoint import TenantCheckpointStore


@dataclass(frozen=True, slots=True)
class RecoveryStatus:
    checkpoints: int
    latest_sequence: int | None
    latest_checksum: str | None
    tenant_checkpoints: int
    latest_tenant_sequence: int | None
    latest_tenant_checksum: str | None
    tenant_aligned: bool
    leader: str | None
    epoch: int


class SwarmRecoveryManager:
    """Own bounded runtime/tenant checkpoints and deterministic failover decisions."""

    def __init__(self, *, max_checkpoints: int = 8) -> None:
        self.store = CheckpointStore(max_checkpoints=max_checkpoints)
        self.tenant_store = TenantCheckpointStore(max_checkpoints=max_checkpoints)
        self.failover = FailoverCoordinator()
        self._replicas: dict[str, ReplicaState] = {}
        self._decision = self.failover.elect(self._replicas)
        self._lock = RLock()

    def checkpoint(self, runtime: SwarmRuntime, tenant_broker: TenantSwarmBroker | None = None) -> int:
        """Capture runtime state and, when provided, tenant ownership at the same sequence."""
        with self._lock:
            checkpoint = self.store.capture(runtime)
            if tenant_broker is not None:
                self.tenant_store.capture(checkpoint.sequence, tenant_broker)
            return checkpoint.sequence

    def restore_latest(self) -> HardenedSwarmRuntime | None:
        with self._lock:
            latest = self.store.latest()
            if latest is None:
                return None
            return HardenedSwarmRuntime.from_state(latest.state, requeue_leased=True)

    def restore_tenants(
        self,
        tenant_broker: TenantSwarmBroker,
        sequence: int | None = None,
    ) -> TenantRepairResult | None:
        """Restore tenant ownership for a runtime checkpoint when sidecar metadata exists."""
        with self._lock:
            target_sequence = sequence
            if target_sequence is None:
                latest = self.store.latest()
                if latest is None:
                    return None
                target_sequence = latest.sequence
            if self.tenant_store.get(target_sequence) is None:
                return None
            return self.tenant_store.restore(tenant_broker, target_sequence)

    def elect(self, replicas: Mapping[str, ReplicaState]) -> str | None:
        with self._lock:
            self._replicas = dict(replicas)
            self._decision = self.failover.elect(self._replicas)
            return self._decision.leader_id

    def status(self) -> RecoveryStatus:
        with self._lock:
            latest = self.store.latest()
            latest_tenant = self.tenant_store.latest()
            runtime_sequence = None if latest is None else latest.sequence
            tenant_sequence = None if latest_tenant is None else latest_tenant.sequence
            return RecoveryStatus(
                checkpoints=len(self.store),
                latest_sequence=runtime_sequence,
                latest_checksum=None if latest is None else latest.checksum,
                tenant_checkpoints=len(self.tenant_store),
                latest_tenant_sequence=tenant_sequence,
                latest_tenant_checksum=None if latest_tenant is None else latest_tenant.checksum,
                tenant_aligned=(tenant_sequence is None or tenant_sequence == runtime_sequence),
                leader=self._decision.leader_id,
                epoch=self._decision.epoch,
            )
