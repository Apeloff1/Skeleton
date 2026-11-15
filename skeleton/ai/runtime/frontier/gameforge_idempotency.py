"""Byte-bounded local retry window. Durable admission must live above it."""
from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
import json
from threading import RLock
from typing import Generic, TypeVar

from skeleton.frontier.payloads import json_snapshot

T = TypeVar("T")


class IdempotencyMismatch(ValueError):
    """An existing key is bound to a different request fingerprint."""


@dataclass(frozen=True)
class IdempotencyStats:
    accepted: int
    duplicates: int
    evicted: int


class IdempotencyWindow(Generic[T]):
    def __init__(self, capacity: int = 1024, *, max_bytes: int = 8 << 20,
                 max_value_bytes: int = 256 << 10) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 65_536:
            raise ValueError("invalid idempotency capacity")
        if (type(max_bytes) is not int or not 1 <= max_bytes <= 64 << 20
                or type(max_value_bytes) is not int
                or not 1 <= max_value_bytes <= min(max_bytes, 8 << 20)):
            raise ValueError("invalid idempotency byte budget")
        self._capacity = capacity
        self._max_bytes = max_bytes
        self._value_bytes = max_value_bytes
        self._values = OrderedDict()
        self._bytes = self._accepted = self._duplicates = self._evicted = 0
        self._lock = RLock()

    @staticmethod
    def _key(key):
        if type(key) is not str or not key.strip() or len(key.encode("utf-8")) > 1024:
            raise ValueError("bounded nonempty idempotency key required")

    @staticmethod
    def _fingerprint(fingerprint):
        if fingerprint is not None and (type(fingerprint) is not str
                or len(fingerprint) != 64
                or any(ch not in "0123456789abcdef" for ch in fingerprint)):
            raise ValueError("fingerprint must be lowercase SHA-256")

    @property
    def capacity(self) -> int:
        return self._capacity

    def record(self, key: str, value: T, *, fingerprint: str | None = None) -> tuple[bool, T]:
        self._key(key)
        self._fingerprint(fingerprint)
        with self._lock:
            prior = self._values.get(key)
            if prior is not None:
                if prior[0] != fingerprint:
                    raise IdempotencyMismatch("conflicting request fingerprint")
                self._duplicates += 1
                return False, json.loads(prior[1])
            raw = json.dumps(json_snapshot(value, max_bytes=self._value_bytes),
                             sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("ascii")
            size = len(raw) + len(key.encode("utf-8")) + (64 if fingerprint else 0)
            if size > self._max_bytes:
                raise ValueError("idempotency entry exceeds aggregate budget")
            while self._values and (len(self._values) >= self._capacity
                                    or self._bytes + size > self._max_bytes):
                _, row = self._values.popitem(last=False)
                self._bytes -= row[2]
                self._evicted += 1
            self._values[key] = (fingerprint, raw, size)
            self._bytes += size
            self._accepted += 1
            return True, json.loads(raw)

    def lookup(self, key: str, *, fingerprint: str | None = None) -> T | None:
        self._key(key)
        self._fingerprint(fingerprint)
        with self._lock:
            row = self._values.get(key)
            if row is None:
                return None
            if row[0] != fingerprint:
                raise IdempotencyMismatch("conflicting request fingerprint")
            return json.loads(row[1])

    @property
    def retained_bytes(self) -> int:
        with self._lock:
            return self._bytes

    def stats(self) -> IdempotencyStats:
        with self._lock:
            return IdempotencyStats(self._accepted, self._duplicates, self._evicted)

    def __len__(self) -> int:
        with self._lock:
            return len(self._values)
