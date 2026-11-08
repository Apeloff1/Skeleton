"""Quarantined event-stream facade reusing canonical authenticated SSE delivery.

The previous implementation returned only an SHA-256 digest of repr(snapshot)
and therefore lost events, cursor, replay and response semantics. A digest is
not a stream. This class delegates to the existing verified ledger, HMAC cursor,
long-poll and bounded SSE encoder. No new public transport is registered.
"""
from __future__ import annotations

import hmac
from collections import deque
from threading import BoundedSemaphore
from time import monotonic_ns

from .contracts import StreamError, StreamPolicy
from .query import StreamQuery
from .reader import StreamSnapshot
from .render import encode
from .service import EventStream


class EventStreamSOTA:
    """Opt-in, strictly owner-scoped wrapper over canonical flight SSE."""

    def __init__(self, ledger, bearer: str, principal: str,
                 *, policy: StreamPolicy | None = None):
        try:
            actual_principal = ledger.identity.key()
            if (type(principal) is not str or type(actual_principal) is not str
                    or not 1 <= len(principal) <= 256
                    or not 1 <= len(actual_principal) <= 256
                    or not hmac.compare_digest(
                        principal.encode("utf-8"), actual_principal.encode("utf-8")
                    )):
                raise StreamError("event stream principal does not own ledger")
        except (AttributeError, TypeError, ValueError, UnicodeError) as exc:
            raise StreamError("authoritative ledger principal required") from exc
        self._stream = EventStream(ledger, bearer, policy=policy)
        self.policy = self._stream.policy
        self.reader = self._stream.reader
        self._slots = BoundedSemaphore(12)
        self.telemetry: deque[dict] = deque(maxlen=128)

    def _encode(self, snapshot: StreamSnapshot) -> bytes:
        # Never return a digest or stringify an untrusted snapshot.
        return encode(snapshot, limit_bytes=self.policy.max_payload_bytes)

    def read(self, query: StreamQuery, *, epoch: int = 0) -> tuple[bytes, dict]:
        if not isinstance(query, StreamQuery):
            raise StreamError("validated stream query required")
        # Canonical cursor MAC does not attest a separate epoch. Do not claim a
        # cross-epoch authenticated cursor feature until the ledger supports it.
        if type(epoch) is not int or epoch != 0:
            raise StreamError("authenticated cursor epoch is not available")
        if not self._slots.acquire(blocking=False):
            raise StreamError("bounded event-stream admission exhausted")
        try:
            start = monotonic_ns()
            raw, record = self._stream.read(query)
            if (type(raw) is not bytes or len(raw) > self.policy.max_payload_bytes
                    or type(record) is not dict
                    or record.get("schema") != "skeleton.ai.flight-snapshot.v1"):
                raise StreamError("invalid canonical event projection")
            receipt = {
                "schema": "event-stream-receipt.v3-sota",
                "epoch": 0,
                "latency_ns": max(0, monotonic_ns() - start),
                "job_id": record["job_id"],
                "state": record["state"],
                "events": record["events"],
                "latest_ordinal": record["latest_ordinal"],
                "terminal": record["terminal"],
                "backlog": record["backlog"],
            }
            self.telemetry.append(receipt)
            return raw, dict(receipt)
        finally:
            self._slots.release()
