"""Durable idempotency records for write endpoints.

Lifecycle of a key within a scope (typically ``tenant:route``)::

    begin()  -> Started (caller executes the write)
             -> Replay  (a completed response exists with the same fingerprint)
             -> InFlight (another owner holds an unexpired lock)
             -> Mismatch (the key was used with a different request fingerprint)
    complete() stores the response; abandon() releases the lock on failure.

A crashed owner's lock expires after ``lock_ttl_s`` and the next caller may
take over. Completed records live until ``ttl_s`` and are then purged.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Mapping, Optional

from skeleton.persistence.pack_h.codecs import canonical_json
from skeleton.persistence.pack_h.migrations import IDEMPOTENCY_MIGRATIONS, connect, migrate

KEY_RE = re.compile(r"^[A-Za-z0-9._:\-]{8,128}$")
MAX_BODY_BYTES = 1024 * 1024


class IdempotencyError(RuntimeError):
    pass


class InvalidKey(IdempotencyError):
    pass


class Outcome(str, Enum):
    STARTED = "started"
    REPLAY = "replay"
    IN_FLIGHT = "in_flight"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status_code: int
    headers: Dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8")) if self.body else None


@dataclass(frozen=True, slots=True)
class BeginResult:
    outcome: Outcome
    scope: str
    key: str
    owner: Optional[str] = None
    response: Optional[StoredResponse] = None
    retry_after_s: float = 0.0


def validate_key(key: Optional[str]) -> str:
    if key is None or not KEY_RE.fullmatch(key):
        raise InvalidKey("Idempotency-Key must be 8-128 chars of [A-Za-z0-9._:-]")
    return key


def fingerprint(method: str, path: str, body: Any, *, extra: Optional[Mapping[str, Any]] = None) -> str:
    """Stable digest of the request semantics a key is bound to."""
    h = hashlib.sha256()
    h.update(method.upper().encode())
    h.update(b"\x00")
    h.update(path.encode("utf-8"))
    h.update(b"\x00")
    if isinstance(body, (bytes, bytearray)):
        h.update(b"b:")
        h.update(bytes(body))
    else:
        h.update(b"j:")
        h.update(canonical_json(body).encode("utf-8"))
    if extra:
        h.update(b"\x00")
        h.update(canonical_json(dict(extra)).encode("utf-8"))
    return h.hexdigest()


def _positive(value: float, name: str) -> float:
    v = float(value)
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return v


class IdempotencyStore:
    def __init__(
        self,
        path: str = ":memory:",
        *,
        ttl_s: float = 86_400.0,
        lock_ttl_s: float = 30.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.ttl_s = _positive(ttl_s, "ttl_s")
        self.lock_ttl_s = _positive(lock_ttl_s, "lock_ttl_s")
        if self.lock_ttl_s > self.ttl_s:
            raise ValueError("lock_ttl_s cannot exceed ttl_s")
        self._clock = clock
        self._conn = connect(path)
        self._lock = threading.RLock()
        with self._lock:
            migrate(self._conn, "idempotency", IDEMPOTENCY_MIGRATIONS)
        self.counters: Dict[str, int] = {o.value: 0 for o in Outcome}
        self.counters["completed"] = 0
        self.counters["abandoned"] = 0
        self.counters["takeovers"] = 0

    def begin(self, scope: str, key: str, fp: str, *, owner: Optional[str] = None) -> BeginResult:
        validate_key(key)
        if not scope:
            raise IdempotencyError("scope is required")
        owner = owner or uuid.uuid4().hex
        now = self._clock()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT fingerprint, state, status_code, headers_json, body, owner, locked_until, expires_at "
                    "FROM pack_h_idempotency WHERE scope = ? AND key = ?",
                    (scope, key),
                ).fetchone()
                result: BeginResult
                if row is not None and float(row[7]) <= now:
                    self._conn.execute("DELETE FROM pack_h_idempotency WHERE scope = ? AND key = ?", (scope, key))
                    row = None
                if row is None:
                    self._conn.execute(
                        "INSERT INTO pack_h_idempotency (scope, key, fingerprint, state, owner, created_at, "
                        "locked_until, expires_at) VALUES (?, ?, ?, 'in_flight', ?, ?, ?, ?)",
                        (scope, key, fp, owner, now, now + self.lock_ttl_s, now + self.ttl_s),
                    )
                    result = BeginResult(Outcome.STARTED, scope, key, owner=owner)
                elif row[0] != fp:
                    result = BeginResult(Outcome.MISMATCH, scope, key)
                elif row[1] == "completed":
                    resp = StoredResponse(
                        status_code=int(row[2]),
                        headers=json.loads(row[3] or "{}"),
                        body=bytes(row[4] or b""),
                    )
                    result = BeginResult(Outcome.REPLAY, scope, key, response=resp)
                elif float(row[6]) <= now:
                    self._conn.execute(
                        "UPDATE pack_h_idempotency SET owner = ?, locked_until = ? WHERE scope = ? AND key = ?",
                        (owner, now + self.lock_ttl_s, scope, key),
                    )
                    self.counters["takeovers"] += 1
                    result = BeginResult(Outcome.STARTED, scope, key, owner=owner)
                else:
                    result = BeginResult(
                        Outcome.IN_FLIGHT, scope, key, retry_after_s=round(max(0.0, float(row[6]) - now), 2)
                    )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            self.counters[result.outcome.value] += 1
        return result

    def complete(
        self,
        scope: str,
        key: str,
        owner: str,
        *,
        status_code: int,
        body: bytes,
        headers: Optional[Mapping[str, str]] = None,
    ) -> bool:
        """Store the response. Returns False if ``owner`` lost the lock."""
        if not 100 <= int(status_code) <= 599:
            raise IdempotencyError("status_code out of range")
        if len(body) > MAX_BODY_BYTES:
            raise IdempotencyError("response body too large to store")
        safe_headers = {
            str(k).lower(): str(v)
            for k, v in (headers or {}).items()
            if str(k).lower() not in {"set-cookie", "authorization", "content-length", "date"}
        }
        with self._lock:
            cur = self._conn.execute(
                "UPDATE pack_h_idempotency SET state = 'completed', status_code = ?, headers_json = ?, body = ? "
                "WHERE scope = ? AND key = ? AND owner = ? AND state = 'in_flight'",
                (int(status_code), json.dumps(safe_headers, sort_keys=True), bytes(body), scope, key, owner),
            )
            ok = (cur.rowcount or 0) == 1
            if ok:
                self.counters["completed"] += 1
        return ok

    def abandon(self, scope: str, key: str, owner: str) -> bool:
        """Release an in-flight record so the client may retry immediately."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM pack_h_idempotency WHERE scope = ? AND key = ? AND owner = ? AND state = 'in_flight'",
                (scope, key, owner),
            )
            ok = (cur.rowcount or 0) == 1
            if ok:
                self.counters["abandoned"] += 1
        return ok

    def purge_expired(self) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM pack_h_idempotency WHERE expires_at <= ?", (self._clock(),))
        return cur.rowcount or 0

    def count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM pack_h_idempotency").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
