"""Exclusive lease contract for bounded ownership transfer.

Leases are single-owner tokens with fail-closed release semantics.  The backing
set serializes capacity accounting so concurrent acquire/release operations
cannot create phantom capacity or drive the counter below zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Callable


@dataclass
class Lease:
    token: str
    _released: bool = False
    _on_release: Callable[[], None] | None = field(default=None, repr=False, compare=False)
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def release(self) -> None:
        with self._lock:
            if self._released:
                raise RuntimeError("lease already released")
            self._released = True
        if self._on_release is not None:
            self._on_release()


class LeaseSet:
    def __init__(self, capacity: int = 64):
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self._cap = capacity
        self._active = 0
        self._lock = Lock()

    def acquire(self, token: str) -> Lease | None:
        if not isinstance(token, str) or not token.strip():
            raise ValueError("token must be a non-empty string")
        with self._lock:
            if self._active >= self._cap:
                return None
            self._active += 1

        def release_slot() -> None:
            with self._lock:
                if self._active <= 0:
                    raise RuntimeError("lease accounting underflow")
                self._active -= 1

        return Lease(token, _on_release=release_slot)

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    @property
    def capacity(self) -> int:
        return self._cap

    @property
    def remaining(self) -> int:
        with self._lock:
            return self._cap - self._active
