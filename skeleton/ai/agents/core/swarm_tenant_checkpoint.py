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
from math import isfinite
from threading import RLock
from time import time
from typing import Callable, Deque

from skeleton.automation.agents.swarm_tenant_broker import TenantRepairResult, TenantSwarmBroker, is_terminal


@dataclass(frozen=True, slots=True)
class TenantMetadataCheckpoint:
    sequence: int
    created_at: float
    checksum: str
    active: tuple[tuple[str, str], ...]
    terminal: tuple[tuple[str, str], ...]
    policy_sha256: str | None = None


class TenantCheckpointStore:
    """Keep tenant metadata aligned with a bounded runtime checkpoint history."""

    def __init__(self, *, max_checkpoints: int = 32, clock: Callable[[], float] = time) -> None:
        if isinstance(max_checkpoints, bool) or not isinstance(max_checkpoints, int) or max_checkpoints < 1:
            raise ValueError("max_checkpoints must be positive")
        self.max_checkpoints = max_checkpoints
        self._clock = clock
        self._items: Deque[TenantMetadataCheckpoint] = deque(maxlen=max_checkpoints)
        self._lock = RLock()

    @staticmethod
    def _checksum(sequence: int, active: tuple[tuple[str, str], ...], terminal: tuple[tuple[str, str], ...],
                  policy_sha256: str | None = None) -> str:
        body = {"sequence": sequence, "active": active, "terminal": terminal}
        if policy_sha256 is not None:
            body["policy_sha256"] = policy_sha256
        encoded = json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    @staticmethod
    def _validate_pairs(label: str, pairs: tuple[tuple[str, str], ...]) -> None:
        seen: set[str] = set()
        for pair in pairs:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError(f"invalid {label} tenant checkpoint record")
            task_id, tenant = pair
            if not isinstance(task_id, str) or task_id.strip() != task_id or not task_id:
                raise ValueError(f"invalid {label} task id")
            if not isinstance(tenant, str) or tenant.strip() != tenant or not tenant:
                raise ValueError(f"invalid {label} tenant id")
            if task_id in seen:
                raise ValueError(f"duplicate {label} task id: {task_id}")
            seen.add(task_id)

    @classmethod
    def _validate_checkpoint(cls, checkpoint: TenantMetadataCheckpoint) -> TenantMetadataCheckpoint:
        if isinstance(checkpoint.sequence, bool) or not isinstance(checkpoint.sequence, int) or checkpoint.sequence < 1:
            raise ValueError("tenant checkpoint sequence must be a positive integer")
        if isinstance(checkpoint.created_at, bool) or not isinstance(checkpoint.created_at, (int, float)):
            raise ValueError("tenant checkpoint created_at must be a finite non-negative number")
        created_at = float(checkpoint.created_at)
        if not isfinite(created_at) or created_at < 0:
            raise ValueError("tenant checkpoint created_at must be a finite non-negative number")
        if not isinstance(checkpoint.checksum, str) or not checkpoint.checksum:
            raise ValueError("tenant checkpoint checksum must not be empty")
        cls._validate_pairs("active", checkpoint.active)
        cls._validate_pairs("terminal", checkpoint.terminal)
        overlap = set(dict(checkpoint.active)).intersection(dict(checkpoint.terminal))
        if overlap:
            raise ValueError(f"tenant checkpoint task appears active and terminal: {sorted(overlap)[0]}")
        if checkpoint.policy_sha256 is not None and (
            type(checkpoint.policy_sha256) is not str or len(checkpoint.policy_sha256) != 64
            or any(c not in "0123456789abcdef" for c in checkpoint.policy_sha256)
        ):
            raise ValueError("invalid tenant policy seal")
        expected = cls._checksum(checkpoint.sequence, checkpoint.active, checkpoint.terminal,
                                 checkpoint.policy_sha256)
        if expected != checkpoint.checksum:
            raise ValueError("tenant checkpoint checksum mismatch")
        return TenantMetadataCheckpoint(
            checkpoint.sequence,
            created_at,
            checkpoint.checksum,
            tuple(checkpoint.active),
            tuple(checkpoint.terminal),
            checkpoint.policy_sha256,
        )

    def capture(self, sequence: int, broker: TenantSwarmBroker) -> TenantMetadataCheckpoint:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("sequence must be positive")
        status = broker.status()
        active = tuple(sorted(dict(status["tenants_by_task"]).items()))
        terminal = tuple(dict(status["terminal_tenants"]).items())
        created_at = self._clock()
        if isinstance(created_at, bool) or not isinstance(created_at, (int, float)) or not isfinite(float(created_at)) or float(created_at) < 0:
            raise RuntimeError("tenant checkpoint clock must return a finite non-negative number")
        seal = broker.ingress.policy_sha256() if broker.verified_mode else None
        checkpoint = TenantMetadataCheckpoint(
            sequence=sequence,
            created_at=float(created_at),
            checksum=self._checksum(sequence, active, terminal, seal),
            active=active,
            terminal=terminal,
            policy_sha256=seal,
        )
        checkpoint = self._validate_checkpoint(checkpoint)
        with self._lock:
            existing = next((item for item in self._items if item.sequence == sequence), None)
            if existing is not None:
                existing = self._validate_checkpoint(existing)
                if existing.checksum != checkpoint.checksum:
                    raise ValueError(f"tenant checkpoint sequence conflict: {sequence}")
                return existing
            if self._items and checkpoint.sequence <= self._items[-1].sequence:
                raise ValueError("tenant checkpoint history must be strictly increasing")
            self._items.append(checkpoint)
        return checkpoint

    def load_verified(self, checkpoint: TenantMetadataCheckpoint) -> TenantMetadataCheckpoint:
        """Append persisted tenant metadata after full checksum and ordering validation."""
        verified = self._validate_checkpoint(checkpoint)
        with self._lock:
            existing = next((item for item in self._items if item.sequence == verified.sequence), None)
            if existing is not None:
                existing = self._validate_checkpoint(existing)
                if existing.checksum != verified.checksum:
                    raise ValueError(f"tenant checkpoint sequence conflict: {verified.sequence}")
                return existing
            if self._items and verified.sequence <= self._items[-1].sequence:
                raise ValueError("tenant checkpoint history must be strictly increasing")
            self._items.append(verified)
            return verified

    def latest(self) -> TenantMetadataCheckpoint | None:
        with self._lock:
            return self._items[-1] if self._items else None

    def get(self, sequence: int) -> TenantMetadataCheckpoint | None:
        with self._lock:
            return next((item for item in self._items if item.sequence == sequence), None)

    def history(self) -> tuple[TenantMetadataCheckpoint, ...]:
        with self._lock:
            return tuple(self._items)

    def discard(self, sequence: int) -> bool:
        """Discard one sidecar checkpoint, used to roll back paired capture failures."""
        with self._lock:
            retained = [item for item in self._items if item.sequence != sequence]
            if len(retained) == len(self._items):
                return False
            self._items = deque(retained, maxlen=self.max_checkpoints)
            return True

    def restore(self, broker: TenantSwarmBroker, sequence: int | None = None) -> TenantRepairResult:
        checkpoint = self.latest() if sequence is None else self.get(sequence)
        if checkpoint is None:
            raise KeyError("tenant checkpoint not found")
        checkpoint = self._validate_checkpoint(checkpoint)
        if len(checkpoint.terminal) > broker.max_terminal_records:
            raise ValueError("tenant checkpoint exceeds target terminal record capacity")
        if broker.verified_mode and len(checkpoint.active) + len(checkpoint.terminal) > broker.max_terminal_records:
            raise ValueError("verified checkpoint exceeds identity retention capacity")

        if checkpoint.policy_sha256 is not None and (
            not broker.verified_mode or broker.ingress.policy_sha256() != checkpoint.policy_sha256
        ):
            raise ValueError("tenant admission policy does not match durable seal")
        status = broker.status()
        if status["tracked_tasks"] or status["terminal_records"] or status["ingress"]["accounted_tasks"]:
            raise ValueError("tenant broker must be empty before metadata restore")

        resident = {task.id: task for task in broker.broker.runtime.tasks()}
        if broker.verified_mode:
            owners = dict(checkpoint.active + checkpoint.terminal)
            if not set(resident) <= set(owners):
                raise ValueError("restored verified runtime contains an unowned task")
            for task in resident.values():
                if any(owners.get(dep) != owners[task.id] for dep in task.dependencies):
                    raise ValueError("restored dependency crosses tenant custody")
        for task_id, _tenant in checkpoint.active:
            task = resident.get(task_id)
            if task is None:
                raise ValueError(f"active tenant task missing from restored runtime: {task_id}")
            if is_terminal(task):
                raise ValueError(f"active tenant task is terminal in restored runtime: {task_id}")
        for task_id, _tenant in checkpoint.terminal:
            task = resident.get(task_id)
            if task is not None and not is_terminal(task):
                raise ValueError(f"terminal tenant task is active in restored runtime: {task_id}")

        with broker._lock, broker.ingress._lock:
            if checkpoint.policy_sha256 is not None and broker.ingress.policy_sha256() != checkpoint.policy_sha256:
                raise ValueError("tenant admission policy changed during restore")
            broker._tenant_by_task = dict(checkpoint.active)
            broker._terminal_tenants = OrderedDict(checkpoint.terminal)
            try:
                return broker.repair()
            except Exception:
                if broker.verified_mode:
                    broker.retire()
                raise

    def sequences(self) -> tuple[int, ...]:
        with self._lock:
            return tuple(item.sequence for item in self._items)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
