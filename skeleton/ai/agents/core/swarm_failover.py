"""Failover coordination primitives for promoting replicated swarm state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ReplicaState:
    replica_id: str
    epoch: int
    sequence: int
    healthy: bool = True


@dataclass(frozen=True, slots=True)
class FailoverDecision:
    leader_id: str | None
    epoch: int
    reason: str


class FailoverCoordinator:
    """Selects a deterministic healthy leader by epoch/sequence/id ordering."""

    def elect(self, replicas: Mapping[str, ReplicaState]) -> FailoverDecision:
        healthy = [replica for replica in replicas.values() if replica.healthy]
        if not healthy:
            return FailoverDecision(None, 0, "no healthy replicas")
        healthy.sort(key=lambda item: (-item.epoch, -item.sequence, item.replica_id))
        leader = healthy[0]
        return FailoverDecision(leader.replica_id, leader.epoch, "highest durable replica state")

    def can_promote(self, candidate: ReplicaState, *, current_epoch: int) -> bool:
        return candidate.healthy and candidate.epoch >= current_epoch
