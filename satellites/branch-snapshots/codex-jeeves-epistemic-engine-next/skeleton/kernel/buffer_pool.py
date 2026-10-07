"""buffer_pool — pre-allocated buffer classes (gameforge-rs buffers::BufferPool port).

Classes 4KB / 64KB / 1MB. A lease returns its buffer to the class on
``release()`` or context-manager exit. Per-class idle cap is ``CLASS_CAP``.

Sibling source: ``/workspace/chaos-scout/gf-buffers.rs``.

Separate from ``skeleton.kernel.leases`` (fencing-token grants) — that
module is left untouched.
"""

from __future__ import annotations

import threading
from enum import Enum
from typing import Any, Dict, List, Optional


CLASS_SMALL = 4096
CLASS_MEDIUM = 65536
CLASS_LARGE = 1 << 20
CLASS_CAP = 64


class Class(Enum):
    """Buffer size class. Names match gameforge-rs ``buffers::Class``."""

    SMALL = CLASS_SMALL
    MEDIUM = CLASS_MEDIUM
    LARGE = CLASS_LARGE


def _class_for(min_size: int) -> Class:
    if min_size <= CLASS_SMALL:
        return Class.SMALL
    if min_size <= CLASS_MEDIUM:
        return Class.MEDIUM
    return Class.LARGE


class Lease:
    """Held buffer. Reclaims into the pool on ``release()`` / ``with`` exit."""

    def __init__(self, buf: bytearray, cls: Class, pool: "BufferPool") -> None:
        self.buf = buf
        self._class = cls
        self._pool: Optional[BufferPool] = pool
        self._released = False

    @property
    def size_class(self) -> Class:
        return self._class

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        pool = self._pool
        self._pool = None
        if pool is not None:
            pool._reclaim(self._class, self.buf)

    def __enter__(self) -> "Lease":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass


class BufferPool:
    """Sync port of gf ``buffers::BufferPool``. Three classes, CLASS_CAP idle each."""

    def __init__(self) -> None:
        self._small: List[bytearray] = []
        self._medium: List[bytearray] = []
        self._large: List[bytearray] = []
        self._leased = 0
        self._lock = threading.Lock()

    @property
    def leased(self) -> int:
        with self._lock:
            return self._leased

    def _lane(self, cls: Class) -> List[bytearray]:
        if cls is Class.SMALL:
            return self._small
        if cls is Class.MEDIUM:
            return self._medium
        return self._large

    def lease(self, min_size: int) -> Lease:
        cls = _class_for(int(min_size))
        cap = int(cls.value)
        with self._lock:
            self._leased += 1
            lane = self._lane(cls)
            buf = lane.pop() if lane else bytearray(cap)
        if len(buf) < cap:
            buf.extend(b"\x00" * (cap - len(buf)))
        return Lease(buf, cls, self)

    def _reclaim(self, cls: Class, buf: bytearray) -> None:
        buf.clear()
        with self._lock:
            self._leased -= 1
            if self._leased < 0:
                self._leased = 0
            lane = self._lane(cls)
            if len(lane) < CLASS_CAP:
                lane.append(buf)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "leased": self._leased,
                "small": len(self._small),
                "medium": len(self._medium),
                "large": len(self._large),
                "class_cap": CLASS_CAP,
            }
