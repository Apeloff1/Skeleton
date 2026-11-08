"""Idempotency-Key replay for unsafe methods, scoped per tenant+route+key."""
from __future__ import annotations

import hashlib
import time
import math
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .envelope import EdgeError


@dataclass
class Stored:
    fingerprint: str
    status: int = 0
    headers: List[Tuple[bytes, bytes]] = field(default_factory=list)
    body: bytes = b""
    done: bool = False
    created: float = 0.0


class IdempotencyCache:
    def __init__(self, ttl_s: float = 86400.0, max_entries: int = 10_000,
                 max_body: int = 1 << 20, clock: Callable[[], float] = time.monotonic):
        if (type(ttl_s) not in (int, float) or not math.isfinite(ttl_s)
                or not 1 <= ttl_s <= 604800 or type(max_entries) is not int
                or not 1 <= max_entries <= 100000 or type(max_body) is not int
                or not 1 <= max_body <= 4 * 1024 * 1024):
            raise ValueError("invalid bounded idempotency configuration")
        self.ttl_s, self.max_entries, self.max_body = ttl_s, max_entries, max_body
        self._clock = clock
        self._data: Dict[str, Stored] = {}
        self._lock = threading.RLock()

    @staticmethod
    def fingerprint(method: str, path: str, body: bytes) -> str:
        return hashlib.sha256(method.encode() + b" " + path.encode() + b"\n" + body).hexdigest()

    def _gc(self) -> None:
        """Locked eviction: never discard an active reservation to make capacity."""
        now = self._clock()
        for key in [key for key, rec in self._data.items()
                    if rec.done and now - rec.created > self.ttl_s]:
            del self._data[key]
        while len(self._data) >= self.max_entries:
            finished = next((key for key, rec in self._data.items() if rec.done), None)
            if finished is None:
                raise EdgeError(503, "EDGE.IDEMPOTENCY.CAPACITY", "idempotency admission capacity exhausted")
            del self._data[finished]

    def begin(self, key: str, fp: str) -> Optional[Stored]:
        """Only the first thread reserves a fresh key; all others replay or block."""
        if (type(key) is not str or not 1 <= len(key) <= 1024
                or type(fp) is not str or len(fp) != 64):
            raise EdgeError(400, "EDGE.IDEMPOTENCY.INVALID", "invalid idempotency identity")
        with self._lock:
            cur = self._data.get(key)
            if cur is not None:
                if cur.fingerprint != fp:
                    raise EdgeError(422, "EDGE.IDEMPOTENCY.MISMATCH", "idempotency key reused with different request")
                if not cur.done:
                    raise EdgeError(409, "EDGE.IDEMPOTENCY.IN_FLIGHT", "request with this key is in progress")
                if self._clock() - cur.created <= self.ttl_s:
                    return cur
                del self._data[key]
            self._gc()
            self._data[key] = Stored(fp, created=self._clock())
            return None

    def complete(self, key: str, status: int, headers, body: bytes) -> None:
        with self._lock:
            cur = self._data.get(key)
            if cur is None:
                return
            if (type(status) is not int or status >= 500
                    or type(body) is not bytes or len(body) > self.max_body):
                del self._data[key]
                return
            cur.status, cur.headers, cur.body, cur.done = status, list(headers), body, True

    def abandon(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
