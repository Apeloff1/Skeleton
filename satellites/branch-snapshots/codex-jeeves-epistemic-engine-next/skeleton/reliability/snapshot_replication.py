"""Snapshot replication — cross-region state replication with lag tracking.

Replicates state snapshots (from backup manager) to peer regions with
monotonic sequence numbers, tracks replication lag per peer, detects
divergence via checksum comparison, and supports catch-up resync.
Feeds readiness signals for DR failover decisions.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Replica:
    region: str
    last_sequence: int = 0
    last_checksum: str = ""
    lag_sequences: int = 0
    healthy: bool = True
    last_sync_ns: int = 0


@dataclass
class SnapshotRecord:
    sequence: int
    payload: Dict[str, Any]
    checksum: str
    timestamp_ns: int


class SnapshotReplicator:
    """Sequenced state replication to peer regions."""

    def __init__(self, max_lag: int = 100):
        self._snapshots: List[SnapshotRecord] = []
        self._replicas: Dict[str, Replica] = {}
        self._sequence = 0
        self.max_lag = max_lag

    def _checksum(self, payload: Dict[str, Any]) -> str:
        return hashlib.sha256(repr(sorted(payload.items())).encode()).hexdigest()[:16]

    def add_replica(self, region: str) -> Replica:
        r = Replica(region=region)
        self._replicas[region] = r
        return r

    def publish(self, payload: Dict[str, Any]) -> SnapshotRecord:
        self._sequence += 1
        record = SnapshotRecord(
            sequence=self._sequence,
            payload=payload,
            checksum=self._checksum(payload),
            timestamp_ns=time.time_ns(),
        )
        self._snapshots.append(record)
        if len(self._snapshots) > 1000:
            self._snapshots.pop(0)
        for r in self._replicas.values():
            r.lag_sequences = self._sequence - r.last_sequence
        return record

    def sync(self, region: str) -> Dict[str, Any]:
        replica = self._replicas.get(region)
        if not replica:
            return {"synced": False, "reason": "unknown replica"}
        missing = [s for s in self._snapshots if s.sequence > replica.last_sequence]
        applied = 0
        divergent = False
        for snap in missing:
            if snap.sequence != replica.last_sequence + 1 and applied == 0 and replica.last_sequence > 0:
                divergent = True
                break
            replica.last_sequence = snap.sequence
            replica.last_checksum = snap.checksum
            applied += 1
        replica.last_sync_ns = time.time_ns()
        replica.lag_sequences = self._sequence - replica.last_sequence
        replica.healthy = not divergent and replica.lag_sequences <= self.max_lag
        return {
            "synced": not divergent,
            "applied": applied,
            "lag": replica.lag_sequences,
            "divergent": divergent,
            "region": region,
        }

    def verify_consistency(self, region: str) -> Dict[str, Any]:
        replica = self._replicas.get(region)
        if not replica:
            return {"consistent": False, "reason": "unknown replica"}
        latest = self._snapshots[-1] if self._snapshots else None
        if not latest:
            return {"consistent": True, "reason": "no snapshots"}
        up_to_date = replica.last_sequence == latest.sequence
        checksum_match = replica.last_checksum == latest.checksum
        return {
            "consistent": up_to_date and checksum_match,
            "up_to_date": up_to_date,
            "checksum_match": checksum_match,
            "replica_sequence": replica.last_sequence,
            "source_sequence": latest.sequence,
        }

    def failover_ready(self, region: str) -> bool:
        replica = self._replicas.get(region)
        return bool(replica and replica.healthy and replica.lag_sequences <= self.max_lag)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "replication-card",
            "sequence": self._sequence,
            "snapshots": len(self._snapshots),
            "replicas": {r: {
                "sequence": rep.last_sequence,
                "lag": rep.lag_sequences,
                "healthy": rep.healthy,
                "failover_ready": self.failover_ready(r),
            } for r, rep in self._replicas.items()},
        }
