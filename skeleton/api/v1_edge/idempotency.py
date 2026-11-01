"""Idempotency-Key replay for unsafe methods, scoped per tenant+route+key."""
from __future__ import annotations

import hashlib
import math
import threading
import time
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
        if isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float)) or not math.isfinite(ttl_s) or ttl_s <= 0:
            raise ValueError("idempotency TTL must be positive and finite")
        if type(max_entries) is not int or max_entries < 1:
            raise ValueError("idempotency max_entries must be positive")
        if type(max_body) is not int or max_body < 1:
            raise ValueError("idempotency max_body must be positive")
        self.ttl_s, self.max_entries, self.max_body = ttl_s, max_entries, max_body
        self._clock = clock
        self._lock = threading.RLock()
        self._data: Dict[str, Stored] = {}

    @staticmethod
    def fingerprint(method: str, path: str, body: bytes) -> str:
        return hashlib.sha256(method.encode() + b" " + path.encode() + b"\n" + body).hexdigest()

    def _gc(self) -> None:
        now = self._clock()
        for k in [k for k, v in self._data.items() if now - v.created > self.ttl_s]:
            del self._data[k]
        if len(self._data) >= self.max_entries:
            # Never evict a live reservation or completed response before TTL.
            # That would reopen an in-flight duplicate or break replay custody.
            raise EdgeError(503, "EDGE.IDEMPOTENCY.CAPACITY", "idempotency capacity exhausted")

    def begin(self, key: str, fp: str) -> Optional[Stored]:
        """Return a completed entry to replay, or None after atomically reserving the key."""
        with self._lock:
            cur = self._data.get(key)
            if cur and self._clock() - cur.created > self.ttl_s:
                del self._data[key]
                cur = None
            if cur is not None:
                if cur.fingerprint != fp:
                    raise EdgeError(422, "EDGE.IDEMPOTENCY.MISMATCH", "idempotency key reused with different request")
                if not cur.done:
                    raise EdgeError(409, "EDGE.IDEMPOTENCY.IN_FLIGHT", "request with this key is in progress")
                return cur
            self._gc()
            self._data[key] = Stored(fp, created=self._clock())
            return None

    def complete(self, key: str, status: int, headers, body: bytes) -> None:
        with self._lock:
            cur = self._data.get(key)
            if cur is None:
                return
            if status >= 500 or len(body) > self.max_body:
                del self._data[key]  # do not pin server failures / huge bodies
                return
            cur.status, cur.headers, cur.body, cur.done = status, list(headers), body, True

    def abandon(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
