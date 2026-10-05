"""Kernel checkpoints — snapshot and restore for restartable state.

Supervisors restart agents; checkpoints decide what survives the
restart. A checkpoint is a versioned, integrity-sealed snapshot of one
component's state, taken at a logical sequence number the component
owns. On recovery the component asks for its latest checkpoint and
resumes from there instead of replaying the world.

Design:

- :class:`Checkpoint` — state bytes (canonical JSON), sequence, SHA-256
  seal, wall + logical timestamps. The seal is recomputed on restore —
  a corrupted or hand-edited snapshot is rejected, never half-applied.
- :class:`CheckpointStore` — per-component retention of the last N
  snapshots, monotonic sequence enforcement (you cannot checkpoint
  backwards), and latest()/restore() with seal verification.

Storage is in-memory here; the store's read/write surface is small
enough to back with disk or the vault later.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Optional, Tuple
from collections import deque

from .errors import KernelError


class CheckpointError(KernelError):
    code = "KRN.CHECKPOINT"


class CheckpointCorruptError(CheckpointError):
    code = "KRN.CKPT_CORRUPT"


class CheckpointSequenceError(CheckpointError):
    code = "KRN.CKPT_SEQUENCE"


def _seal(component: str, sequence: int, state: Dict[str, Any]) -> str:
    canonical = json.dumps(
        {"component": component, "sequence": sequence, "state": state},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Checkpoint:
    component: str
    sequence: int
    state: Dict[str, Any]
    taken_at: float
    seal: str

    @classmethod
    def create(cls, component: str, sequence: int,
               state: Dict[str, Any], *, now: float) -> "Checkpoint":
        if sequence < 0:
            raise CheckpointError(
                "sequence must be non-negative",
                context={"component": component, "sequence": sequence},
            )
        return cls(component=component, sequence=sequence, state=dict(state),
                   taken_at=now, seal=_seal(component, sequence, state))

    def verify(self) -> None:
        expected = _seal(self.component, self.sequence, self.state)
        if expected != self.seal:
            raise CheckpointCorruptError(
                "checkpoint seal mismatch — refusing to restore",
                context={"component": self.component,
                         "sequence": self.sequence,
                         "expected": expected[:12],
                         "actual": self.seal[:12]},
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component": self.component,
            "sequence": self.sequence,
            "state": self.state,
            "taken_at": self.taken_at,
            "seal": self.seal,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        ckpt = cls(
            component=data["component"],
            sequence=int(data["sequence"]),
            state=dict(data["state"]),
            taken_at=float(data["taken_at"]),
            seal=data["seal"],
        )
        ckpt.verify()
        return ckpt


class CheckpointStore:
    """Bounded, per-component checkpoint retention."""

    def __init__(self, *, retain: int = 3,
                 clock: Optional[Callable[[], float]] = None) -> None:
        if retain < 1:
            raise CheckpointError("retain must be >= 1",
                                  context={"retain": retain})
        self.retain = retain
        self._now = clock or time.time
        self._stores: Dict[str, Deque[Checkpoint]] = {}
        self._high_seq: Dict[str, int] = {}

    def save(self, component: str, sequence: int,
             state: Dict[str, Any]) -> Checkpoint:
        last = self._high_seq.get(component, -1)
        if sequence <= last:
            raise CheckpointSequenceError(
                "checkpoint sequence must increase monotonically",
                context={"component": component,
                         "attempted": sequence, "latest": last},
            )
        ckpt = Checkpoint.create(component, sequence, state, now=self._now())
        store = self._stores.setdefault(component, deque(maxlen=self.retain))
        store.append(ckpt)
        self._high_seq[component] = sequence
        return ckpt

    def latest(self, component: str) -> Optional[Checkpoint]:
        store = self._stores.get(component)
        return store[-1] if store else None

    def restore(self, component: str,
                *, min_sequence: int = 0) -> Optional[Checkpoint]:
        """Newest verified checkpoint at or above min_sequence. Walks back
        past any corrupted entries rather than trusting the newest blindly."""
        store = self._stores.get(component)
        if not store:
            return None
        for ckpt in reversed(store):
            if ckpt.sequence < min_sequence:
                break
            try:
                ckpt.verify()
            except CheckpointCorruptError:
                continue
            return ckpt
        return None

    def history(self, component: str) -> Tuple[Checkpoint, ...]:
        return tuple(self._stores.get(component, ()))

    def components(self) -> Tuple[str, ...]:
        return tuple(sorted(self._stores))

    def report(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "retained": len(store),
                "latest_sequence": store[-1].sequence if store else None,
                "latest_seal": store[-1].seal[:12] if store else None,
            }
            for name, store in sorted(self._stores.items())
        }
