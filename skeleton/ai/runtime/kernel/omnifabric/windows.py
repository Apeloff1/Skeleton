"""Hot-tail windows and compaction checkpoints for OmniFabric.

When the hot tail drains, historical events leave process memory. This
module seals drained ranges into ``FabricWindow`` checkpoints so verify
and projections can still reason about history without holding every
event hot.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from skeleton.kernel.omnifabric.codecs import sha256_hex, stable_json
from skeleton.kernel.omnifabric.events import FabricEvent
from skeleton.kernel.omnifabric.verify import merkle_root_of, verify_events


@dataclass
class FabricWindow:
    window_id: str
    start_seq: int
    end_seq: int
    start_prev_hash: str
    end_hash: str
    event_count: int
    merkle_root: str
    sealed_at: float = field(default_factory=time.time)
    ledger_counts: dict[str, int] = field(default_factory=dict)
    kind_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "start_seq": self.start_seq,
            "end_seq": self.end_seq,
            "start_prev_hash": self.start_prev_hash,
            "end_hash": self.end_hash,
            "event_count": self.event_count,
            "merkle_root": self.merkle_root,
            "sealed_at": self.sealed_at,
            "ledger_counts": dict(self.ledger_counts),
            "kind_counts": dict(self.kind_counts),
        }


def seal_window(events: Sequence[FabricEvent], *, window_id: str | None = None) -> FabricWindow:
    if not events:
        raise ValueError("cannot seal empty window")
    ordered = sorted(events, key=lambda e: e.seq)
    report = verify_events(ordered)
    if not report.ok:
        raise ValueError(f"cannot seal broken window: {report.issues[0].detail}")
    ledgers: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for ev in ordered:
        ledgers[ev.ledger] = ledgers.get(ev.ledger, 0) + 1
        kinds[ev.kind] = kinds.get(ev.kind, 0) + 1
    wid = window_id or sha256_hex(
        f"{ordered[0].seq}:{ordered[-1].seq}:{ordered[-1].hash}"
    )[:16]
    return FabricWindow(
        window_id=wid,
        start_seq=ordered[0].seq,
        end_seq=ordered[-1].seq,
        start_prev_hash=ordered[0].prev_hash,
        end_hash=ordered[-1].hash,
        event_count=len(ordered),
        merkle_root=merkle_root_of(ordered),
        ledger_counts=ledgers,
        kind_counts=kinds,
    )


class WindowStore:
    """Ordered store of sealed fabric windows."""

    def __init__(self, *, max_windows: int = 8192) -> None:
        self._max = int(max_windows)
        self._lock = threading.RLock()
        self._windows: list[FabricWindow] = []

    def add(self, window: FabricWindow) -> None:
        with self._lock:
            if self._windows and window.start_seq <= self._windows[-1].end_seq:
                raise ValueError(
                    f"window overlap: new start {window.start_seq} <= "
                    f"last end {self._windows[-1].end_seq}"
                )
            if self._windows and window.start_prev_hash != self._windows[-1].end_hash:
                raise ValueError("window does not chain from previous end_hash")
            self._windows.append(window)
            if len(self._windows) > self._max:
                self._windows = self._windows[-self._max :]

    def list_windows(self) -> list[FabricWindow]:
        with self._lock:
            return list(self._windows)

    def head(self) -> FabricWindow | None:
        with self._lock:
            return self._windows[-1] if self._windows else None

    def verify_links(self) -> bool:
        with self._lock:
            for a, b in zip(self._windows, self._windows[1:]):
                if b.start_prev_hash != a.end_hash:
                    return False
                if b.start_seq != a.end_seq + 1:
                    return False
            return True

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "window_count": len(self._windows),
                "max_windows": self._max,
                "total_events": sum(w.event_count for w in self._windows),
                "head": self._windows[-1].to_dict() if self._windows else None,
            }

    def export(self) -> list[dict[str, Any]]:
        with self._lock:
            return [w.to_dict() for w in self._windows]
