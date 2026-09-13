"""Checkpoint and failover coordination for swarm runtime recovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.agents.swarm_checkpoint import CheckpointStore
from skeleton.agents.swarm_failover import FailoverCoordinator
from skeleton.agents.swarm_runtime import SwarmRuntime


@dataclass(frozen=True, slots=True)
class RecoveryStatus:
    checkpoints: int
    latest_revision: int | None
    leader: str | None
    members: tuple[str, ...]


class SwarmRecoveryManager:
    """Owns bounded checkpoints plus deterministic control-plane leadership."""

    def __init__(self, *, max_checkpoints: int = 8, node_id: str = "local") -> None:
        self.store = CheckpointStore(max_checkpoints=max_checkpoints)
        self.failover = FailoverCoordinator(node_id=node_id)

    def checkpoint(self, runtime: SwarmRuntime) -> int:
        return self.store.save(runtime.export_state()).revision

    def restore_latest(self) -> SwarmRuntime | None:
        item = self.store.latest()
        if item is None:
            return None
        return SwarmRuntime.from_state(item.state, requeue_leased=True)

    def set_members(self, members: Iterable[str]) -> str | None:
        self.failover.set_members(members)
        return self.failover.leader()

    def status(self) -> RecoveryStatus:
        latest = self.store.latest()
        return RecoveryStatus(
            checkpoints=len(self.store),
            latest_revision=None if latest is None else latest.revision,
            leader=self.failover.leader(),
            members=self.failover.members(),
        )
