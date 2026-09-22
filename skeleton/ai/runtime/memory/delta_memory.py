"""Δ-Memory — bounded windowed delta store (gameforge-rs port).

Every write lands as a delta in a bounded window; when the window fills it
compacts into a snapshot. Footprint is capped by construction — the window
never grows past ``window_cap`` deltas.

Sibling source: ``/workspace/chaos-scout/gf-delta_memory.rs``
(``gf-gameforge`` ``delta_memory::DeltaMemory``).

Distinct from ``backend/gameforge/omega/delta_memory.py`` (KDA associative
matrix). This module is the RS *window* semantics port.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple


class DeltaMemory:
    """Windowed key→value store: deltas compact into a snapshot when full."""

    def __init__(self, window_cap: int = 512) -> None:
        if window_cap < 1:
            raise ValueError("window_cap must be >= 1")
        self.window_cap = int(window_cap)
        self._window: List[Tuple[str, Any]] = []
        self._snapshot: Dict[str, Any] = {}
        self.compactions = 0
        self._lock = threading.RLock()

    def write(self, key: str, value: Any) -> None:
        """Append a delta; compact into snapshot when the window is full."""
        with self._lock:
            self._window.append((str(key), value))
            if len(self._window) >= self.window_cap:
                for k, v in self._window:
                    self._snapshot[k] = v
                self._window.clear()
                self.compactions += 1

    def read(self, key: str) -> Optional[Any]:
        """Latest value: window (newest first) then snapshot."""
        key = str(key)
        with self._lock:
            for k, v in reversed(self._window):
                if k == key:
                    return v
            return self._snapshot.get(key)

    def compact(self) -> int:
        """Force-compact any pending window deltas into the snapshot."""
        with self._lock:
            if not self._window:
                return 0
            n = len(self._window)
            for k, v in self._window:
                self._snapshot[k] = v
            self._window.clear()
            self.compactions += 1
            return n

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "window_len": len(self._window),
                "snapshot_keys": len(self._snapshot),
                "window_cap": self.window_cap,
                "compactions": self.compactions,
            }


__all__ = ["DeltaMemory"]
