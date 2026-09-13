"""Versioned bounded checkpoints for swarm runtime recovery."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from threading import RLock
from time import time
from typing import Callable, Deque

from skeleton.agents.swarm_runtime import SwarmRuntime
from skeleton.agents.swarm_snapshot import normalize_snapshot


@dataclass(frozen=True, slots=True)
class Checkpoint:
    sequence: int
    created_at: float
    checksum: str
    state: dict[str, object]


class CheckpointStore:
    """Thread-safe bounded checkpoint history with checksum verification."""

    def __init__(self, *, max_checkpoints: int = 32, clock: Callable[[], float] = time) -> None:
        if isinstance(max_checkpoints, bool) or not isinstance(max_checkpoints, int) or max_checkpoints < 1:
            raise ValueError("max_checkpoints must be positive")
        self.max_checkpoints = max_checkpoints
        self._clock = clock
        self._sequence = 0
        self._items: Deque[Checkpoint] = deque(maxlen=max_checkpoints)
        self._lock = RLock()

    @staticmethod
    def _encoded(state: dict[str, object]) -> bytes:
        return json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    @classmethod
    def _checksum(cls, state: dict[str, object]) -> str:
        return sha256(cls._encoded(state)).hexdigest()

    @staticmethod
    def _clone(checkpoint: Checkpoint) -> Checkpoint:
        return Checkpoint(
            checkpoint.sequence,
            checkpoint.created_at,
            checkpoint.checksum,
            deepcopy(checkpoint.state),
        )

    @classmethod
    def _validate(cls, checkpoint: Checkpoint) -> Checkpoint:
        if isinstance(checkpoint.sequence, bool) or not isinstance(checkpoint.sequence, int) or checkpoint.sequence < 1:
            raise ValueError("checkpoint sequence must be a positive integer")
        if isinstance(checkpoint.created_at, bool) or not isinstance(checkpoint.created_at, (int, float)):
            raise ValueError("checkpoint created_at must be a finite non-negative number")
        created_at = float(checkpoint.created_at)
        if not isfinite(created_at) or created_at < 0:
            raise ValueError("checkpoint created_at must be a finite non-negative number")
        if not isinstance(checkpoint.checksum, str) or not checkpoint.checksum:
            raise ValueError("checkpoint checksum must not be empty")
        if not isinstance(checkpoint.state, dict):
            raise ValueError("checkpoint state must be a dictionary")
        state = normalize_snapshot(deepcopy(checkpoint.state))
        expected = cls._checksum(state)
        if checkpoint.checksum != expected:
            raise ValueError("checkpoint checksum mismatch")
        return Checkpoint(checkpoint.sequence, created_at, checkpoint.checksum, state)

    def capture(self, runtime: SwarmRuntime) -> Checkpoint:
        state = normalize_snapshot(runtime.export_state())
        created_at = self._clock()
        if isinstance(created_at, bool) or not isinstance(created_at, (int, float)) or not isfinite(float(created_at)) or float(created_at) < 0:
            raise RuntimeError("checkpoint clock must return a finite non-negative number")
        with self._lock:
            self._sequence += 1
            checkpoint = Checkpoint(
                self._sequence,
                float(created_at),
                self._checksum(state),
                deepcopy(state),
            )
            self._items.append(checkpoint)
            return self._clone(checkpoint)

    def load_verified(self, checkpoint: Checkpoint) -> Checkpoint:
        """Append a persisted checkpoint after full checksum and ordering validation."""
        verified = self._validate(checkpoint)
        with self._lock:
            existing = next((item for item in self._items if item.sequence == verified.sequence), None)
            if existing is not None:
                if existing.checksum != verified.checksum:
                    raise ValueError(f"checkpoint sequence conflict: {verified.sequence}")
                return self._clone(existing)
            if self._items and verified.sequence <= self._items[-1].sequence:
                raise ValueError("checkpoint history must be strictly increasing")
            self._items.append(self._clone(verified))
            self._sequence = max(self._sequence, verified.sequence)
            return self._clone(verified)

    def latest(self) -> Checkpoint | None:
        with self._lock:
            return None if not self._items else self._clone(self._items[-1])

    def get(self, sequence: int) -> Checkpoint | None:
        with self._lock:
            checkpoint = next((item for item in self._items if item.sequence == sequence), None)
            return None if checkpoint is None else self._clone(checkpoint)

    def history(self) -> tuple[Checkpoint, ...]:
        with self._lock:
            return tuple(self._clone(item) for item in self._items)

    def discard(self, sequence: int) -> bool:
        """Discard one checkpoint without rewinding the monotonic sequence counter."""
        with self._lock:
            retained = [item for item in self._items if item.sequence != sequence]
            if len(retained) == len(self._items):
                return False
            self._items = deque(retained, maxlen=self.max_checkpoints)
            return True

    def restore(self, sequence: int | None = None) -> SwarmRuntime:
        checkpoint = self.latest() if sequence is None else self.get(sequence)
        if checkpoint is None:
            raise KeyError("checkpoint not found")
        verified = self._validate(checkpoint)
        return SwarmRuntime.from_state(verified.state)

    def sequences(self) -> tuple[int, ...]:
        with self._lock:
            return tuple(item.sequence for item in self._items)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
