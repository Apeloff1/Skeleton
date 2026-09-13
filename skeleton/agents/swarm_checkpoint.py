"""Versioned bounded checkpoints for swarm runtime recovery."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
import json
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
    def __init__(self, *, max_checkpoints: int = 32, clock: Callable[[], float] = time) -> None:
        if max_checkpoints < 1:
            raise ValueError("max_checkpoints must be positive")
        self.max_checkpoints = max_checkpoints
        self._clock = clock
        self._sequence = 0
        self._items: Deque[Checkpoint] = deque(maxlen=max_checkpoints)

    def capture(self, runtime: SwarmRuntime) -> Checkpoint:
        state = normalize_snapshot(runtime.export_state())
        encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        self._sequence += 1
        checkpoint = Checkpoint(self._sequence, self._clock(), sha256(encoded).hexdigest(), state)
        self._items.append(checkpoint)
        return checkpoint

    def latest(self) -> Checkpoint | None:
        return self._items[-1] if self._items else None

    def get(self, sequence: int) -> Checkpoint | None:
        return next((item for item in self._items if item.sequence == sequence), None)

    def restore(self, sequence: int | None = None) -> SwarmRuntime:
        checkpoint = self.latest() if sequence is None else self.get(sequence)
        if checkpoint is None:
            raise KeyError("checkpoint not found")
        return SwarmRuntime.from_state(checkpoint.state)

    def __len__(self) -> int:
        return len(self._items)
