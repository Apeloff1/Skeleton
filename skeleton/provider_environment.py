"""GF-P0-16: exact game environment adapters, deterministic replay, holdout isolation.

Builds on :class:`skeleton.simulation.world_model.EnvironmentAdapter`; does not
fork it. All buffers are bounded (see GF-P0-18 resource envelopes).
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from skeleton.simulation.world_model import EnvironmentAdapter


class EnvironmentMismatchError(RuntimeError):
    """Requested environment identity does not exactly match the registered one."""


class HoldoutLeakError(RuntimeError):
    """A holdout example was routed into training/replay data."""


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EnvironmentIdentity:
    simulation_id: str
    build_digest: str
    seed: int

    def key(self) -> str:
        return f"{self.simulation_id}@{self.build_digest}#{self.seed}"


class ExactEnvironmentRegistry:
    """Only returns an adapter whose simulation id, build digest and seed match exactly."""

    def __init__(self, *, max_environments: int = 256) -> None:
        if max_environments <= 0:
            raise ValueError("max_environments must be positive")
        self.max_environments = max_environments
        self._items: dict[str, tuple[EnvironmentIdentity, EnvironmentAdapter]] = {}
        self._lock = threading.RLock()

    def register(self, identity: EnvironmentIdentity, adapter: EnvironmentAdapter) -> None:
        if not isinstance(adapter, EnvironmentAdapter):
            raise TypeError("adapter does not implement EnvironmentAdapter")
        if adapter.simulation_id != identity.simulation_id or adapter.seed != identity.seed:
            raise EnvironmentMismatchError("adapter does not match declared identity")
        with self._lock:
            if identity.key() not in self._items and len(self._items) >= self.max_environments:
                raise RuntimeError("environment registry capacity exhausted")
            self._items[identity.key()] = (identity, adapter)

    def resolve(self, identity: EnvironmentIdentity) -> EnvironmentAdapter:
        with self._lock:
            entry = self._items.get(identity.key())
        if entry is None:
            raise EnvironmentMismatchError(f"no exact environment for {identity.key()}")
        return entry[1]


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    example_id: str
    environment_key: str
    payload_digest: str
    payload: Mapping[str, Any]


class HoldoutSplit:
    """Deterministic hash-based split; holdout ids can never enter training data."""

    def __init__(self, *, salt: str, holdout_fraction: float) -> None:
        if not 0.0 < holdout_fraction < 1.0:
            raise ValueError("holdout_fraction must be in (0, 1)")
        if not salt:
            raise ValueError("salt is required")
        self.salt = salt
        self.holdout_fraction = holdout_fraction

    def is_holdout(self, example_id: str) -> bool:
        h = hashlib.sha256(f"{self.salt}:{example_id}".encode()).digest()
        return int.from_bytes(h[:8], "big") / 2**64 < self.holdout_fraction


class BoundedRecordBuffer:
    """FIFO record store capped by item count; evicts oldest on overflow."""

    def __init__(self, *, max_items: int) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self.max_items = max_items
        self._records: deque[ReplayRecord] = deque()
        self._lock = threading.RLock()
        self.evicted = 0

    def _append(self, record: ReplayRecord) -> None:
        with self._lock:
            self._records.append(record)
            while len(self._records) > self.max_items:
                self._records.popleft()
                self.evicted += 1

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def records(self) -> tuple[ReplayRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def digest(self) -> str:
        return _digest([(r.example_id, r.payload_digest) for r in self.records()])


class HoldoutBuffer(BoundedRecordBuffer):
    def __init__(self, split: HoldoutSplit, *, max_items: int) -> None:
        super().__init__(max_items=max_items)
        self.split = split

    def add(self, record: ReplayRecord) -> None:
        if not self.split.is_holdout(record.example_id):
            raise HoldoutLeakError("non-holdout example routed to holdout buffer")
        self._append(record)


class DeterministicReplayBuffer(BoundedRecordBuffer):
    """Training replay; rejects holdout ids and samples reproducibly from a seed."""

    def __init__(self, split: HoldoutSplit, *, max_items: int) -> None:
        super().__init__(max_items=max_items)
        self.split = split

    def add(self, record: ReplayRecord) -> None:
        if self.split.is_holdout(record.example_id):
            raise HoldoutLeakError("holdout example routed to training replay")
        self._append(record)

    def sample(self, k: int, *, seed: int) -> tuple[ReplayRecord, ...]:
        items = self.records()
        rng = random.Random(f"{seed}:{self.digest()}")
        return tuple(rng.sample(items, min(k, len(items))))


def route_records(
    records: Iterable[ReplayRecord],
    replay: DeterministicReplayBuffer,
    holdout: HoldoutBuffer,
) -> None:
    if replay.split is not holdout.split:
        raise ValueError("replay and holdout must share one split")
    for record in records:
        (holdout if replay.split.is_holdout(record.example_id) else replay).add(record)


def make_record(example_id: str, identity: EnvironmentIdentity, payload: Mapping[str, Any]) -> ReplayRecord:
    return ReplayRecord(example_id, identity.key(), _digest(dict(payload)), dict(payload))


def replay_episode(
    adapter: EnvironmentAdapter, actions: Iterable[Mapping[str, object]]
) -> str:
    """Reset and replay actions; returns a digest of the state trajectory."""

    states = [_digest(dict(adapter.reset()))]
    for action in actions:
        adapter.step(action)
        states.append(_digest(dict(adapter.state)))
    return _digest(states)


__all__ = [
    "BoundedRecordBuffer", "DeterministicReplayBuffer", "EnvironmentIdentity",
    "EnvironmentMismatchError", "ExactEnvironmentRegistry", "HoldoutBuffer",
    "HoldoutLeakError", "HoldoutSplit", "ReplayRecord", "make_record",
    "replay_episode", "route_records",
]
