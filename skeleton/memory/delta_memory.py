"""Δ-Memory — bounded windowed delta store (gameforge-rs port).

Every write lands as a delta in a bounded window; when the window fills it
compacts into a snapshot. Footprint is capped by construction — the window
never grows past ``window_cap`` deltas.

RS source: ``gf-gameforge::delta_memory::DeltaMemory``
(``/workspace/gameforge-rs/crates/gf-gameforge/src/lib.rs``; sibling copy
``/workspace/chaos-scout/gf-delta_memory.rs``).

RS parity (core surface, unchanged from #1649):
- ``write`` appends ``(key, value)``; when ``len(window) >= window_cap`` the
  window drains into the snapshot (last write wins) and ``compactions += 1``.
- ``read`` scans the window newest-first, then falls back to the snapshot.
- ``stats`` reports ``window_len`` / ``snapshot_keys`` / ``compactions``
  (plus ``window_cap`` and extended counters as additive keys).

Extensions (Python-side, extend-only): tombstone deletes, batch writes,
materialized views, export/load state, and snapshot persistence ports.

Distinct from ``backend/gameforge/omega/delta_memory.py`` (KDA associative
matrix). This module is the RS *window* semantics port — extend-only; does
not touch OmniFabric, SagaRegistry, Diet, Court, or API lifespan.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

DEFAULT_WINDOW_CAP = 512

# Tombstone marker for delete-as-delta (survives until compacted away).
_TOMBSTONE: object = object()


@dataclass(frozen=True, slots=True)
class DeltaMemoryStats:
    """Snapshot of Δ-Memory counters (JSON-friendly via ``as_dict``)."""

    window_len: int
    snapshot_keys: int
    window_cap: int
    compactions: int
    writes: int
    reads: int
    deletes: int
    pending_tombstones: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "window_len": self.window_len,
            "snapshot_keys": self.snapshot_keys,
            "window_cap": self.window_cap,
            "compactions": self.compactions,
            "writes": self.writes,
            "reads": self.reads,
            "deletes": self.deletes,
            "pending_tombstones": self.pending_tombstones,
        }


@runtime_checkable
class DeltaSnapshotPort(Protocol):
    """Persistence port for compacted snapshots (hex adapter boundary)."""

    def save_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        """Persist a full compacted key→value map."""
        ...

    def load_snapshot(self) -> Dict[str, Any]:
        """Return previously persisted snapshot (empty dict if none)."""
        ...


class InMemoryDeltaSnapshotStore:
    """Ephemeral snapshot port — useful for tests and process-local wiring."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self.saves = 0

    def save_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        self._data = dict(snapshot)
        self.saves += 1

    def load_snapshot(self) -> Dict[str, Any]:
        return dict(self._data)


class JsonFileDeltaSnapshotStore:
    """Atomic JSON-file snapshot store (best-effort load; hard fail on save)."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.saves = 0

    def save_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"snapshot": dict(snapshot), "version": 1}
        tmp.write_text(json.dumps(payload, default=str, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)
        self.saves += 1

    def load_snapshot(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        snap = raw.get("snapshot", raw) if isinstance(raw, dict) else {}
        return dict(snap) if isinstance(snap, dict) else {}


class DeltaMemory:
    """Windowed key→value store: deltas compact into a snapshot when full.

    Semantics match ``gf-gameforge::delta_memory``:
    - ``write`` appends ``(key, value)`` to the window
    - when ``len(window) >= window_cap``, drain window into snapshot (last wins)
    - ``read`` scans window newest-first, then snapshot
    """

    def __init__(
        self,
        window_cap: int = DEFAULT_WINDOW_CAP,
        *,
        on_compact: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> None:
        if window_cap < 1:
            raise ValueError("window_cap must be >= 1")
        self.window_cap = int(window_cap)
        self._window: List[Tuple[str, Any]] = []
        self._snapshot: Dict[str, Any] = {}
        self.compactions = 0
        self._writes = 0
        self._reads = 0
        self._deletes = 0
        self._on_compact = on_compact
        self._lock = threading.RLock()

    # -- core RS surface -------------------------------------------------

    def write(self, key: str, value: Any) -> None:
        """Append a delta; compact into snapshot when the window is full."""
        with self._lock:
            self._window.append((str(key), value))
            self._writes += 1
            if len(self._window) >= self.window_cap:
                self._compact_locked()

    def read(self, key: str) -> Optional[Any]:
        """Latest value: window (newest first) then snapshot. Tombstones → None."""
        key = str(key)
        with self._lock:
            self._reads += 1
            for k, v in reversed(self._window):
                if k == key:
                    return None if v is _TOMBSTONE else v
            if key not in self._snapshot:
                return None
            return self._snapshot[key]

    def compact(self) -> int:
        """Force-compact any pending window deltas into the snapshot."""
        with self._lock:
            if not self._window:
                return 0
            n = len(self._window)
            self._compact_locked()
            return n

    def stats(self) -> Dict[str, Any]:
        """RS-compatible stats dict plus extended counters."""
        return self.stats_obj().as_dict()

    def stats_obj(self) -> DeltaMemoryStats:
        with self._lock:
            tombs = sum(1 for _, v in self._window if v is _TOMBSTONE)
            return DeltaMemoryStats(
                window_len=len(self._window),
                snapshot_keys=len(self._snapshot),
                window_cap=self.window_cap,
                compactions=self.compactions,
                writes=self._writes,
                reads=self._reads,
                deletes=self._deletes,
                pending_tombstones=tombs,
            )

    # -- extended hex slice ----------------------------------------------

    def delete(self, key: str) -> bool:
        """Tombstone ``key`` via a window delta. Returns True if key was visible."""
        key = str(key)
        with self._lock:
            existed = self._visible_locked(key)
            self._window.append((key, _TOMBSTONE))
            self._deletes += 1
            if len(self._window) >= self.window_cap:
                self._compact_locked()
            return existed

    def has(self, key: str) -> bool:
        """True when a non-tombstone value is visible for ``key``."""
        with self._lock:
            return self._visible_locked(str(key))

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self.has(key)

    def write_many(self, items: Iterable[Tuple[str, Any]]) -> int:
        """Batch-append deltas. Returns number of writes applied."""
        n = 0
        with self._lock:
            for key, value in items:
                self._window.append((str(key), value))
                self._writes += 1
                n += 1
                if len(self._window) >= self.window_cap:
                    self._compact_locked()
        return n

    def keys(self) -> List[str]:
        """Sorted keys currently visible (snapshot ∪ window, minus tombstones)."""
        with self._lock:
            return sorted(self._materialize_locked())

    def items(self) -> List[Tuple[str, Any]]:
        """Sorted ``(key, value)`` pairs for the materialized view."""
        with self._lock:
            merged = self._materialize_locked()
            return sorted(merged.items(), key=lambda kv: kv[0])

    def materialize(self) -> Dict[str, Any]:
        """Return a copy of the fully merged key→value map."""
        with self._lock:
            return self._materialize_locked()

    def clear(self) -> None:
        """Drop window and snapshot; counters retained for observability."""
        with self._lock:
            self._window.clear()
            self._snapshot.clear()

    def export_state(self) -> Dict[str, Any]:
        """Serializable state for persistence hooks (window + snapshot)."""
        with self._lock:
            window = [
                [k, None if v is _TOMBSTONE else v, v is _TOMBSTONE]
                for k, v in self._window
            ]
            return {
                "version": 1,
                "window_cap": self.window_cap,
                "compactions": self.compactions,
                "writes": self._writes,
                "reads": self._reads,
                "deletes": self._deletes,
                "snapshot": dict(self._snapshot),
                "window": window,
            }

    def load_state(self, state: Mapping[str, Any]) -> None:
        """Restore from ``export_state`` / external snapshot payload."""
        if not isinstance(state, Mapping):
            raise TypeError("state must be a mapping")
        with self._lock:
            snap = state.get("snapshot", {})
            if not isinstance(snap, Mapping):
                raise TypeError("snapshot must be a mapping")
            self._snapshot = {str(k): v for k, v in snap.items()}
            window_raw = state.get("window", [])
            restored: List[Tuple[str, Any]] = []
            if isinstance(window_raw, list):
                for entry in window_raw:
                    if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                        continue
                    k = str(entry[0])
                    if len(entry) >= 3 and entry[2]:
                        restored.append((k, _TOMBSTONE))
                    else:
                        restored.append((k, entry[1]))
            self._window = restored
            if "compactions" in state:
                self.compactions = int(state["compactions"])
            if "writes" in state:
                self._writes = int(state["writes"])
            if "reads" in state:
                self._reads = int(state["reads"])
            if "deletes" in state:
                self._deletes = int(state["deletes"])
            # Cap may be restored only when valid; keep ctor value otherwise.
            if "window_cap" in state:
                cap = int(state["window_cap"])
                if cap >= 1:
                    self.window_cap = cap
            # Preserve the bounded-window invariant for restored payloads.
            if len(self._window) >= self.window_cap:
                self._compact_locked()

    def apply_snapshot(self, snapshot: Mapping[str, Any], *, replace: bool = True) -> None:
        """Load a compacted snapshot (e.g. from ``DeltaSnapshotPort``)."""
        with self._lock:
            if replace:
                self._snapshot = {str(k): v for k, v in snapshot.items()}
            else:
                self._snapshot.update({str(k): v for k, v in snapshot.items()})

    # -- internals -------------------------------------------------------

    def _compact_locked(self) -> None:
        for k, v in self._window:
            if v is _TOMBSTONE:
                self._snapshot.pop(k, None)
            else:
                self._snapshot[k] = v
        self._window.clear()
        self.compactions += 1
        if self._on_compact is not None:
            self._on_compact(dict(self._snapshot))

    def _visible_locked(self, key: str) -> bool:
        for k, v in reversed(self._window):
            if k == key:
                return v is not _TOMBSTONE
        return key in self._snapshot

    def _materialize_locked(self) -> Dict[str, Any]:
        merged = dict(self._snapshot)
        for k, v in self._window:
            if v is _TOMBSTONE:
                merged.pop(k, None)
            else:
                merged[k] = v
        return merged

    def __len__(self) -> int:
        with self._lock:
            return len(self._materialize_locked())

    def __repr__(self) -> str:
        st = self.stats()
        return (
            f"DeltaMemory(window_cap={st['window_cap']}, "
            f"window_len={st['window_len']}, snapshot_keys={st['snapshot_keys']}, "
            f"compactions={st['compactions']})"
        )


class PersistingDeltaMemory:
    """Δ-Memory façade that flushes compacted snapshots through a port.

    Pending window deltas stay in-process until compact (auto or manual).
    On construction, loads any prior snapshot from the port.
    """

    def __init__(
        self,
        port: DeltaSnapshotPort,
        *,
        window_cap: int = DEFAULT_WINDOW_CAP,
        restore: bool = True,
    ) -> None:
        self._port = port
        self._inner = DeltaMemory(
            window_cap=window_cap,
            on_compact=self._persist_snapshot,
        )
        if restore:
            loaded = port.load_snapshot()
            if loaded:
                self._inner.apply_snapshot(loaded, replace=True)

    @property
    def inner(self) -> DeltaMemory:
        return self._inner

    def _persist_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        self._port.save_snapshot(snapshot)

    def write(self, key: str, value: Any) -> None:
        self._inner.write(key, value)

    def read(self, key: str) -> Optional[Any]:
        return self._inner.read(key)

    def delete(self, key: str) -> bool:
        return self._inner.delete(key)

    def compact(self) -> int:
        return self._inner.compact()

    def flush(self) -> int:
        """Force compact + persist. Returns compacted delta count."""
        return self._inner.compact()

    def stats(self) -> Dict[str, Any]:
        return self._inner.stats()

    def materialize(self) -> Dict[str, Any]:
        return self._inner.materialize()

    def has(self, key: str) -> bool:
        return self._inner.has(key)


def build_delta_memory(
    window_cap: int = DEFAULT_WINDOW_CAP,
    *,
    persist_path: Optional[Path | str] = None,
) -> DeltaMemory | PersistingDeltaMemory:
    """Factory: plain ``DeltaMemory`` or file-backed ``PersistingDeltaMemory``."""
    if persist_path is None:
        return DeltaMemory(window_cap=window_cap)
    store = JsonFileDeltaSnapshotStore(persist_path)
    return PersistingDeltaMemory(store, window_cap=window_cap)


__all__ = [
    "DEFAULT_WINDOW_CAP",
    "DeltaMemory",
    "DeltaMemoryStats",
    "DeltaSnapshotPort",
    "InMemoryDeltaSnapshotStore",
    "JsonFileDeltaSnapshotStore",
    "PersistingDeltaMemory",
    "build_delta_memory",
]
