"""Bounded checkpoint sidecar for tenant ownership metadata.

Runtime snapshots intentionally remain tenant-agnostic. This store binds tenant metadata
to the runtime checkpoint sequence so cold recovery can reconstruct ownership and then
reconcile quota/fair-share accounting from the restored runtime.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from hashlib import sha256
import json
from threading import RLock
from time import time
from typing import Callable, Deque

from skeleton.agents.swarm_tenant_broker import TenantRepairResult, TenantSwarmBroker


@dataclass(frozen=True, slots=True)
class TenantMetadataCheckpoint:
    sequence: int
    created_at: float
    checksum: str
    active: tuple[tuple[str, str], ...]
    terminal: tuple[tuple[str, str], ...]


class TenantCheckpointStore:
    """Keep tenant metadata aligned with a bounded runtime checkpoint history."""

    def __init__(self, *, max_checkpoints: int = 32, clock: Callable[[], float] = time) -> None:
        if max_checkpoints < 1:
            raise ValueError("max_checkpoints must be positive")
        self.max_checkpoints = max_checkpoints
        self._clock = clock
        self._items: Deque[TenantMetadataCheckpoint] = deque(maxlen=max_checkpoints)
        self._lock = RLock()

    @staticmethod
    def _checksum(sequence: int, active: tuple[tuple[str, str], ...], terminal: tuple[tuple[str, str], ...]) -> str:
        encoded = json.dumps(
            {"sequence": sequence, "active": active, "terminal": terminal},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def capture(self, sequence: int, broker: TenantSwarmBroker) -> TenantMetadataCheckpoint:
        if sequence < 1:
            raise ValueError("sequence must be positive")
        status = broker.status()
        active = tuple(sorted(dict(status["tenants_by_task"]).items()))
        terminal = tuple(dict(status["terminal_tenants"]).items())
        checkpoint = TenantMetadataCheckpoint(
            sequence=sequence,
            created_at=self._clock(),
            checksum=self._checksum(sequence, active, terminal),
            active=active,
            terminal=terminal,
        )
        with self._lock:
            existing = next((item for item in self._items if item.sequence == sequence), None)
            if existing is not None:
                if existing.checksum != checkpoint.checksum:
                    raise ValueError(f"tenant checkpoint sequence conflict: {sequence}")
                return existing
            self._items.append(checkpoint)
        return checkpoint

    def latest(self) -> TenantMetadataCheckpoint | None:
        with self._lock:
            return self._items[-1] if self._items else None

    def get(self, sequence: int) -> TenantMetadataCheckpoint | None:
        with self._lock:
            return next((item for item in self._items if item.sequence == sequence), None)

    def restore(self, broker: TenantSwarmBroker, sequence: int | None = None) -> TenantRepairResult:
        checkpoint = self.latest() if sequence is None else self.get(sequence)
        if checkpoint is None:
            raise KeyError("tenant checkpoint not found")
        expected = self._checksum(checkpoint.sequence, checkpoint.active, checkpoint.terminal)
        if expected != checkpoint.checksum:
            raise ValueError("tenant checkpoint checksum mismatch")

        status = broker.status()
        if status["tracked_tasks"] or status["terminal_records"] or status["ingress"]["accounted_tasks"]:
            raise ValueError("tenant broker must be empty before metadata restore")

        with broker._lock:
            broker._tenant_by_task = dict(checkpoint.active)
            broker._terminal_tenants = OrderedDict(checkpoint.terminal)
        return broker.repair()

    def sequences(self) -> tuple[int, ...]:
        with self._lock:
            return tuple(item.sequence for item in self._items)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
