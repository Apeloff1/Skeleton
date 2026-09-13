"""Checkpoint and failover coordination for swarm runtime recovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from skeleton.agents.swarm_checkpoint import CheckpointStore
from skeleton.agents.swarm_failover import FailoverCoordinator, ReplicaState
from skeleton.agents.swarm_runtime import SwarmRuntime


@dataclass(frozen=True, slots=True)
class RecoveryStatus:
    checkpoints: int
    latest_sequence: int | None
    latest_checksum: str | None
    leader: str | None
    epoch: int


class SwarmRecoveryManager:
    """Own bounded checkpoints and deterministic failover decisions."""

    def __init__(self, *, max_checkpoints: int = 8) -> None:
        self.store = CheckpointStore(max_checkpoints=max_checkpoints)
        self.failover = FailoverCoordinator()
        self._replicas: dict[str, ReplicaState] = {}
        self._decision = self.failover.elect(self._replicas)

    def checkpoint(self, runtime: SwarmRuntime) -> int:
        return self.store.capture(runtime).sequence

    def restore_latest(self) -> SwarmRuntime | None:
        if self.store.latest() is None:
            return None
        return self.store.restore()

    def elect(self, replicas: Mapping[str, ReplicaState]) -> str | None:
        self._replicas = dict(replicas)
        self._decision = self.failover.elect(self._replicas)
        return self._decision.leader_id

    def status(self) -> RecoveryStatus:
        latest = self.store.latest()
        return RecoveryStatus(
            checkpoints=len(self.store),
            latest_sequence=None if latest is None else latest.sequence,
            latest_checksum=None if latest is None else latest.checksum,
            leader=self._decision.leader_id,
            epoch=self._decision.epoch,
        )
