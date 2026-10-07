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

RS parity extras (additive):
- ``lookup`` / ``get`` mirror RS ``Option<Value>``: a stored ``None`` (JSON
  ``null``) is distinguishable from an absent key, which plain ``read``
  cannot express.
- ``json_values=True`` mirrors RS ``serde_json::Value`` storage: values are
  validated as strict JSON at write time (non-finite floats rejected, tuples
  become lists, map keys become strings) and reads return independent
  copies, so callers can never mutate stored state (RS ``read`` clones).
  Default stays ``False`` so the #1649 reference semantics are unchanged.
- Documented divergence: RS ``new(0)`` compacts on every write; Python keeps
  rejecting ``window_cap < 1`` (#1649 contract) — use ``window_cap=1``.

Distinct from ``backend/gameforge/omega/delta_memory.py`` (KDA associative
matrix). This module is the RS *window* semantics port — extend-only; does
not touch OmniFabric, SagaRegistry, Diet, Court, or API lifespan.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
import time
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

# Sentinel for "key absent" in ``get`` (distinct from a stored ``None``).
_MISSING: object = object()


def _json_clone(value: Any) -> Any:
    """Strict JSON round-trip (RS ``serde_json::Value`` parity).

    Raises ``ValueError`` for non-finite floats and ``TypeError`` for values
    JSON cannot represent, before any state is touched.
    """
    return json.loads(json.dumps(value, allow_nan=False))


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
class DeltaMetricsSink(Protocol):
    """Duck-typed metrics port; ``observability.MetricsRegistry`` satisfies it."""

    def counter(self, name: str, value: float = 1.0,
                labels: Optional[Dict[str, str]] = None) -> None: ...

    def gauge(self, name: str, value: float,
              labels: Optional[Dict[str, str]] = None) -> None: ...

    def observe(self, name: str, value: float,
                labels: Optional[Dict[str, str]] = None) -> None: ...


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


SNAPSHOT_FILE_VERSION = 2


def _snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    blob = json.dumps(snapshot, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class DeltaSnapshotCorrupt(ValueError):
    """A snapshot file failed structural or checksum validation."""


class JsonFileDeltaSnapshotStore:
    """Crash-safe JSON-file snapshot store.

    Save: unique temp file in the target directory, ``fsync``, previous good
    file preserved as ``<name>.bak`` (hard link, no window where neither
    exists), atomic ``os.replace``, best-effort directory ``fsync``. Saves are
    serialized per store instance.

    Load: validates structure, version and the SHA-256 checksum (v2 files;
    v1 files without a checksum still load). A corrupt primary is moved
    aside to ``<name>.corrupt-<ns>`` (never silently overwritten, so it can
    be inspected) and the ``.bak`` is used instead. Returns ``{}`` only when
    nothing valid exists — the #2022 contract.

    ``strict=True`` refuses non-JSON values on save instead of stringifying
    them (``default=str`` stays the default for back-compat).
    """

    def __init__(
        self,
        path: Path | str,
        *,
        strict: bool = False,
        keep_backup: bool = True,
        fsync: bool = True,
    ) -> None:
        self.path = Path(path)
        self.strict = bool(strict)
        self.keep_backup = bool(keep_backup)
        self.fsync = bool(fsync)
        self.saves = 0
        self.recoveries = 0
        self.quarantined: List[Path] = []
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def backup_path(self) -> Path:
        return self.path.with_name(self.path.name + ".bak")

    def save_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        snap = dict(snapshot)
        dumps_kw: Dict[str, Any] = {"sort_keys": True}
        if not self.strict:
            dumps_kw["default"] = str
        else:
            dumps_kw["allow_nan"] = False
        # Serialize before touching disk so a bad value never leaves debris.
        body = json.dumps(snap, **dumps_kw)
        normalized = json.loads(body)
        payload = json.dumps(
            {
                "version": SNAPSHOT_FILE_VERSION,
                "sha256": _snapshot_digest(normalized),
                "snapshot": normalized,
            },
            sort_keys=True,
        )
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = _mkstemp_for(self.path)
            tmp = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                    fh.flush()
                    if self.fsync:
                        os.fsync(fh.fileno())
                if self.keep_backup and self.path.exists():
                    self._preserve_backup()
                os.replace(tmp, self.path)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
            if self.fsync:
                _fsync_dir(self.path.parent)
            self.saves += 1

    def load_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            if self.path.exists():
                try:
                    return _read_snapshot_file(self.path)
                except (OSError, DeltaSnapshotCorrupt) as exc:
                    self.last_error = f"{self.path.name}: {exc}"
                    self._quarantine(self.path)
            bak = self.backup_path
            if self.keep_backup and bak.exists():
                try:
                    snap = _read_snapshot_file(bak)
                except (OSError, DeltaSnapshotCorrupt) as exc:
                    self.last_error = f"{bak.name}: {exc}"
                    self._quarantine(bak)
                    return {}
                self.recoveries += 1
                return snap
            return {}

    def _preserve_backup(self) -> None:
        bak = self.backup_path
        link_tmp = bak.with_name(f"{bak.name}.{os.getpid()}.{time.time_ns()}")
        try:
            os.link(self.path, link_tmp)
        except OSError:
            # Filesystems without hard links: copy (primary stays in place).
            link_tmp.write_bytes(self.path.read_bytes())
        os.replace(link_tmp, bak)

    def _quarantine(self, target: Path) -> None:
        dest = target.with_name(f"{target.name}.corrupt-{time.time_ns()}")
        try:
            os.replace(target, dest)
        except OSError:
            return
        self.quarantined.append(dest)


def _mkstemp_for(path: Path) -> Tuple[int, str]:
    return tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _read_snapshot_file(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeltaSnapshotCorrupt(f"unparseable: {exc}") from exc
    if not isinstance(raw, dict):
        raise DeltaSnapshotCorrupt("top-level payload is not an object")
    if "snapshot" not in raw:
        # Legacy bare map written by external tooling (#2022 accepted it).
        return dict(raw)
    snap = raw["snapshot"]
    if not isinstance(snap, dict):
        raise DeltaSnapshotCorrupt("snapshot is not an object")
    version = raw.get("version", 1)
    if not isinstance(version, int) or version < 1 or version > SNAPSHOT_FILE_VERSION:
        raise DeltaSnapshotCorrupt(f"unsupported version {version!r}")
    if version >= 2:
        expected = raw.get("sha256")
        if not isinstance(expected, str) or expected != _snapshot_digest(snap):
            raise DeltaSnapshotCorrupt("checksum mismatch")
    return dict(snap)


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
        json_values: bool = False,
        metrics: Optional[DeltaMetricsSink] = None,
        metrics_prefix: str = "delta_memory",
        metrics_labels: Optional[Dict[str, str]] = None,
    ) -> None:
        if window_cap < 1:
            raise ValueError("window_cap must be >= 1")
        self.window_cap = int(window_cap)
        self.json_values = bool(json_values)
        self._window: List[Tuple[str, Any]] = []
        self._snapshot: Dict[str, Any] = {}
        self.compactions = 0
        self._writes = 0
        self._reads = 0
        self._deletes = 0
        self._on_compact = on_compact
        self._lock = threading.RLock()
        self._metrics = metrics
        self._metrics_prefix = str(metrics_prefix)
        self._metrics_labels = dict(metrics_labels) if metrics_labels else None
        self.metrics_errors = 0

    # -- core RS surface -------------------------------------------------

    def write(self, key: str, value: Any) -> None:
        """Append a delta; compact into snapshot when the window is full."""
        value = self._ingest(value)
        with self._lock:
            self._window.append((str(key), value))
            self._writes += 1
            self._emit("counter", "writes", 1.0)
            if len(self._window) >= self.window_cap:
                self._compact_locked()

    def read(self, key: str) -> Optional[Any]:
        """Latest value: window (newest first) then snapshot. Tombstones → None."""
        key = str(key)
        with self._lock:
            self._reads += 1
            self._emit("counter", "reads", 1.0)
            for k, v in reversed(self._window):
                if k == key:
                    return None if v is _TOMBSTONE else self._egress(v)
            if key not in self._snapshot:
                return None
            return self._egress(self._snapshot[key])

    def lookup(self, key: str) -> Tuple[bool, Any]:
        """RS ``Option`` parity: ``(found, value)``.

        ``(True, None)`` means a stored ``None``/JSON ``null``; ``(False,
        None)`` means absent or tombstoned. Counts as a read.
        """
        key = str(key)
        with self._lock:
            self._reads += 1
            self._emit("counter", "reads", 1.0)
            for k, v in reversed(self._window):
                if k == key:
                    if v is _TOMBSTONE:
                        return False, None
                    return True, self._egress(v)
            if key in self._snapshot:
                return True, self._egress(self._snapshot[key])
            return False, None

    def get(self, key: str, default: Any = None) -> Any:
        """Like ``read`` but returns ``default`` only when the key is absent."""
        found, value = self.lookup(key)
        return value if found else default

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
            self._emit("counter", "deletes", 1.0)
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
        if self.json_values:
            # Validate the whole batch up front so a bad value cannot leave a
            # half-applied batch behind.
            items = [(str(k), _json_clone(v)) for k, v in items]
        with self._lock:
            for key, value in items:
                self._window.append((str(key), value))
                self._writes += 1
                self._emit("counter", "writes", 1.0)
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
            merged = self._egress(self._materialize_locked())
            return sorted(merged.items(), key=lambda kv: kv[0])

    def materialize(self) -> Dict[str, Any]:
        """Return a copy of the fully merged key→value map."""
        with self._lock:
            return self._egress(self._materialize_locked())

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
                "snapshot": self._egress(dict(self._snapshot)),
                "window": self._egress(window),
            }

    def load_state(self, state: Mapping[str, Any]) -> None:
        """Restore one complete state atomically; malformed recovery fails closed."""
        if not isinstance(state, Mapping):
            raise TypeError("state must be a mapping")

        version=state.get("version",1)
        if isinstance(version,bool) or not isinstance(version,int) or version!=1:
            raise ValueError("unsupported delta memory state version")

        snap=state.get("snapshot",{})
        if not isinstance(snap,Mapping):
            raise TypeError("snapshot must be a mapping")
        new_snapshot={str(k):self._ingest(v) for k,v in snap.items()}

        window_raw=state.get("window",[])
        if not isinstance(window_raw,list):
            raise TypeError("window must be a list")
        new_window:List[Tuple[str,Any]]=[]
        for index,entry in enumerate(window_raw):
            if not isinstance(entry,(list,tuple)) or len(entry) not in {2,3}:
                raise ValueError(
                    f"window entry {index} must contain key, value and optional tombstone"
                )
            tombstone=False
            if len(entry)==3:
                if not isinstance(entry[2],bool):
                    raise TypeError(
                        f"window entry {index} tombstone flag must be boolean"
                    )
                tombstone=entry[2]
            key=str(entry[0])
            new_window.append(
                (key,_TOMBSTONE if tombstone else self._ingest(entry[1]))
            )

        def counter(name:str,current:int,*,minimum:int=0)->int:
            if name not in state:
                return current
            value=state[name]
            if isinstance(value,bool) or not isinstance(value,int) or value<minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
            return value

        new_compactions=counter("compactions",self.compactions)
        new_writes=counter("writes",self._writes)
        new_reads=counter("reads",self._reads)
        new_deletes=counter("deletes",self._deletes)
        new_cap=counter("window_cap",self.window_cap,minimum=1)
        if len(new_window)>=new_cap:
            raise ValueError(
                "restored window violates bounded-window invariant"
            )

        with self._lock:
            self._snapshot=new_snapshot
            self._window=new_window
            self.compactions=new_compactions
            self._writes=new_writes
            self._reads=new_reads
            self._deletes=new_deletes
            self.window_cap=new_cap

    def apply_snapshot(self, snapshot: Mapping[str, Any], *, replace: bool = True) -> None:
        """Load a compacted snapshot (e.g. from ``DeltaSnapshotPort``)."""
        incoming = {str(k): self._ingest(v) for k, v in snapshot.items()}
        with self._lock:
            if replace:
                self._snapshot = incoming
            else:
                self._snapshot.update(incoming)

    # -- internals -------------------------------------------------------

    def _ingest(self, value: Any) -> Any:
        return _json_clone(value) if self.json_values else value

    def _egress(self, value: Any) -> Any:
        return copy.deepcopy(value) if self.json_values else value

    def publish_metrics(self) -> Dict[str, Any]:
        """Push current stats as gauges to the metrics sink; returns stats."""
        st = self.stats()
        with self._lock:
            for name in ("window_len", "snapshot_keys", "pending_tombstones"):
                self._emit("gauge", name, float(st[name]))
        return st

    def _emit(self, kind: str, name: str, value: float) -> None:
        sink = self._metrics
        if sink is None:
            return
        try:
            getattr(sink, kind)(
                f"{self._metrics_prefix}_{name}", value, self._metrics_labels
            )
        except Exception:  # metrics must never break the data path
            self.metrics_errors += 1

    def _compact_locked(self) -> None:
        drained = len(self._window)
        for k, v in self._window:
            if v is _TOMBSTONE:
                self._snapshot.pop(k, None)
            else:
                self._snapshot[k] = v
        self._window.clear()
        self.compactions += 1
        self._emit("counter", "compactions", 1.0)
        self._emit("observe", "compaction_deltas", float(drained))
        self._emit("gauge", "snapshot_keys", float(len(self._snapshot)))
        if self._on_compact is not None:
            self._on_compact(self._egress(dict(self._snapshot)))

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

    Save failures are fail-loud: the exception propagates to the caller of
    the write that triggered compaction, in-memory state stays consistent,
    ``persist_failures`` / ``last_persist_error`` record it, and the store is
    marked dirty so the next ``flush()`` re-persists the full snapshot even
    when the window is empty.
    """

    def __init__(
        self,
        port: DeltaSnapshotPort,
        *,
        window_cap: int = DEFAULT_WINDOW_CAP,
        restore: bool = True,
        json_values: bool = False,
        metrics: Optional[DeltaMetricsSink] = None,
        metrics_prefix: str = "delta_memory",
        metrics_labels: Optional[Dict[str, str]] = None,
    ) -> None:
        self._port = port
        self.persist_failures = 0
        self.last_persist_error: Optional[str] = None
        self._dirty = False
        self._inner = DeltaMemory(
            window_cap=window_cap,
            on_compact=self._persist_snapshot,
            json_values=json_values,
            metrics=metrics,
            metrics_prefix=metrics_prefix,
            metrics_labels=metrics_labels,
        )
        if restore:
            loaded = port.load_snapshot()
            if loaded:
                self._inner.apply_snapshot(loaded, replace=True)

    @property
    def inner(self) -> DeltaMemory:
        return self._inner

    @property
    def dirty(self) -> bool:
        """True when the last snapshot save failed and has not been retried."""
        return self._dirty

    def _persist_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        try:
            self._port.save_snapshot(snapshot)
        except Exception as exc:
            self.persist_failures += 1
            self.last_persist_error = f"{type(exc).__name__}: {exc}"
            self._dirty = True
            self._inner._emit("counter", "persist_failures", 1.0)
            raise
        self._dirty = False

    def write(self, key: str, value: Any) -> None:
        self._inner.write(key, value)

    def write_many(self, items: Iterable[Tuple[str, Any]]) -> int:
        return self._inner.write_many(items)

    def read(self, key: str) -> Optional[Any]:
        return self._inner.read(key)

    def lookup(self, key: str) -> Tuple[bool, Any]:
        return self._inner.lookup(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._inner.get(key, default)

    def delete(self, key: str) -> bool:
        return self._inner.delete(key)

    def compact(self) -> int:
        return self._inner.compact()

    def flush(self) -> int:
        """Force compact + persist. Returns compacted delta count.

        With an empty window, re-saves the snapshot only if a previous save
        failed (``dirty``), so a transient I/O error is recoverable.
        """
        n = self._inner.compact()
        if n == 0 and self._dirty:
            with self._inner._lock:
                self._persist_snapshot(self._inner._egress(dict(self._inner._snapshot)))
        return n

    def stats(self) -> Dict[str, Any]:
        st = self._inner.stats()
        st["persist_failures"] = self.persist_failures
        st["dirty"] = self._dirty
        return st

    def publish_metrics(self) -> Dict[str, Any]:
        self._inner.publish_metrics()
        return self.stats()

    def materialize(self) -> Dict[str, Any]:
        return self._inner.materialize()

    def keys(self) -> List[str]:
        return self._inner.keys()

    def items(self) -> List[Tuple[str, Any]]:
        return self._inner.items()

    def has(self, key: str) -> bool:
        return self._inner.has(key)

    def __contains__(self, key: object) -> bool:
        return key in self._inner

    def __len__(self) -> int:
        return len(self._inner)


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


# -- memory-hex port + adapter registry ---------------------------------


@runtime_checkable
class DeltaMemoryPort(Protocol):
    """Hex port for Δ-Memory consumers.

    Both ``DeltaMemory`` and ``PersistingDeltaMemory`` satisfy it; callers
    depend on this surface, adapters are chosen by name at wiring time via
    ``create_delta_memory``.
    """

    def write(self, key: str, value: Any) -> None: ...

    def read(self, key: str) -> Optional[Any]: ...

    def lookup(self, key: str) -> Tuple[bool, Any]: ...

    def delete(self, key: str) -> bool: ...

    def compact(self) -> int: ...

    def stats(self) -> Dict[str, Any]: ...

    def materialize(self) -> Dict[str, Any]: ...


DeltaMemoryFactory = Callable[..., DeltaMemoryPort]

_ADAPTERS: Dict[str, DeltaMemoryFactory] = {}
_ADAPTERS_LOCK = threading.Lock()


def register_delta_memory_adapter(
    name: str, factory: DeltaMemoryFactory, *, replace: bool = False
) -> None:
    """Register a named Δ-Memory adapter factory (extend-only by default)."""
    key = str(name).strip()
    if not key:
        raise ValueError("adapter name is required")
    if not callable(factory):
        raise TypeError("factory must be callable")
    with _ADAPTERS_LOCK:
        if key in _ADAPTERS and not replace:
            raise ValueError(f"delta memory adapter {key!r} already registered")
        _ADAPTERS[key] = factory


def delta_memory_adapters() -> List[str]:
    """Sorted names of registered adapters."""
    with _ADAPTERS_LOCK:
        return sorted(_ADAPTERS)


def create_delta_memory(adapter: str = "memory", **kwargs: Any) -> DeltaMemoryPort:
    """Build a Δ-Memory through a registered adapter; result must honor the port."""
    with _ADAPTERS_LOCK:
        factory = _ADAPTERS.get(str(adapter).strip())
    if factory is None:
        raise KeyError(
            f"unknown delta memory adapter {adapter!r}; known: {delta_memory_adapters()}"
        )
    built = factory(**kwargs)
    if not isinstance(built, DeltaMemoryPort):
        raise TypeError(f"adapter {adapter!r} did not return a DeltaMemoryPort")
    return built


def _json_file_adapter(
    *, path: Path | str, strict: bool = False, fsync: bool = True, **kwargs: Any
) -> PersistingDeltaMemory:
    store = JsonFileDeltaSnapshotStore(path, strict=strict, fsync=fsync)
    return PersistingDeltaMemory(store, **kwargs)


def _in_memory_persisting_adapter(**kwargs: Any) -> PersistingDeltaMemory:
    return PersistingDeltaMemory(InMemoryDeltaSnapshotStore(), **kwargs)


register_delta_memory_adapter("memory", DeltaMemory)
register_delta_memory_adapter("json_file", _json_file_adapter)
register_delta_memory_adapter("in_memory_persisting", _in_memory_persisting_adapter)


__all__ = [
    "DEFAULT_WINDOW_CAP",
    "DeltaMemory",
    "DeltaMemoryFactory",
    "DeltaMemoryPort",
    "DeltaMemoryStats",
    "DeltaMetricsSink",
    "DeltaSnapshotCorrupt",
    "DeltaSnapshotPort",
    "InMemoryDeltaSnapshotStore",
    "JsonFileDeltaSnapshotStore",
    "PersistingDeltaMemory",
    "SNAPSHOT_FILE_VERSION",
    "build_delta_memory",
    "create_delta_memory",
    "delta_memory_adapters",
    "register_delta_memory_adapter",
]
