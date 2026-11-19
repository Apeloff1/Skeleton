"""Bounded exclusive process-local lease ownership."""
from __future__ import annotations

from threading import Lock
from collections.abc import Callable


class Lease:
    def __init__(self, token: str, *, _on_release: Callable[[], None] | None = None):
        self._token = token
        self._released = False
        self._on_release = _on_release
        self._lock = Lock()

    @property
    def token(self):
        return self._token

    def release(self) -> None:
        with self._lock:
            if self._released:
                raise RuntimeError("lease already released")
            if self._on_release is not None:
                self._on_release()
            self._released = True


class LeaseSet:
    def __init__(self, capacity: int = 64):
        if type(capacity) is not int or not 1 <= capacity <= 65_536:
            raise ValueError("bounded positive capacity required")
        self._cap = capacity
        self._active = {}
        self._lock = Lock()

    def acquire(self, token: str) -> Lease | None:
        if type(token) is not str or not token.strip() or len(token) > 1024:
            raise ValueError("token must be a bounded non-empty string")
        with self._lock:
            if len(self._active) >= self._cap or token in self._active:
                return None

            def release_slot() -> None:
                with self._lock:
                    if self._active.get(token) is not lease:
                        raise RuntimeError("lease ownership mismatch")
                    del self._active[token]

            lease = Lease(token, _on_release=release_slot)
            self._active[token] = lease
            return lease

    @property
    def active(self) -> int:
        with self._lock:
            return len(self._active)

    @property
    def capacity(self) -> int:
        return self._cap

    @property
    def remaining(self) -> int:
        return self._cap - self.active
