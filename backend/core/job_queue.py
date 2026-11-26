"""Durable MongoDB-backed background jobs: leases, retries, idempotency, dead letters.

Several routes start work with a bare ``asyncio.create_task``: if the process
restarts, the job is lost and its status document stays ``running`` forever,
and a transient failure is never retried. This module is the durable
alternative.

Model (one document per job in ``background_jobs``):

* ``enqueue`` inserts a ``queued`` job. An optional ``idempotency_key`` makes
  enqueue safe to retry: the same key with the same payload returns the
  original job, and the same key with a *different* payload raises
  :class:`IdempotencyConflict`. A unique partial index enforces this, which
  also holds across replicas.
* ``claim`` atomically leases the oldest due job (``queued`` and
  ``run_at <= now``, or ``running`` with an expired lease, which recovers jobs
  from crashed workers). Each claim mints a fresh ``lease_token``, and every
  later state change is fenced on that token, so a worker whose lease was
  taken over cannot overwrite the new owner's result.
* ``fail`` re-queues with capped exponential backoff and full jitter until
  ``max_attempts`` is reached, then moves the job to ``dead`` (the dead-letter
  state), keeping the error history. :class:`NonRetryableError` dead-letters
  immediately. ``redrive`` returns a dead job to the queue for an operator.
* :class:`JobWorker` runs registered async handlers with a lease heartbeat.

Error text stored on jobs is the exception type plus a bounded message, never
the payload.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import random
import secrets
import socket
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

log = logging.getLogger("codedock.jobs")

JOBS_COLLECTION = "background_jobs"
STATUSES = ("queued", "running", "succeeded", "dead")
_DUPLICATE_KEY = 11000
_MAX_ERROR_CHARS = 500
_MAX_ERROR_HISTORY = 20

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


class JobQueueError(RuntimeError):
    """Base class for queue errors."""


class IdempotencyConflict(JobQueueError):
    """The idempotency key was already used with a different payload."""


class LeaseLost(JobQueueError):
    """The caller no longer holds the job's lease (expired and re-claimed)."""


class NonRetryableError(Exception):
    """Raise from a handler to dead-letter the job without further attempts."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    base_delay_s: float = 2.0
    max_delay_s: float = 300.0
    multiplier: float = 2.0

    def delay(self, attempt: int, rng: Callable[[], float] = random.random) -> float:
        """Full-jitter backoff for the retry after ``attempt`` (1-based)."""
        ceiling = min(self.max_delay_s, self.base_delay_s * self.multiplier ** max(0, attempt - 1))
        return ceiling * rng()


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: str
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    lease_token: str


def _now() -> datetime:
    return datetime.now(UTC)


def payload_digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _error_text(error: BaseException | str) -> str:
    if isinstance(error, BaseException):
        text = f"{type(error).__name__}: {error}"
    else:
        text = str(error)
    return text[:_MAX_ERROR_CHARS]


class JobQueue:
    def __init__(
        self,
        db: Any,
        *,
        collection: str = JOBS_COLLECTION,
        lease_s: float = 60.0,
        retry: RetryPolicy | None = None,
        clock: Callable[[], datetime] = _now,
        rng: Callable[[], float] = random.random,
    ) -> None:
        if lease_s <= 0:
            raise ValueError("lease_s must be positive")
        self._coll = db[collection]
        self._lease = timedelta(seconds=lease_s)
        self._retry = retry or RetryPolicy()
        self._clock = clock
        self._rng = rng

    async def ensure_indexes(self) -> None:
        await self._coll.create_index([("status", 1), ("run_at", 1)])
        await self._coll.create_index([("status", 1), ("lease_expires_at", 1)])
        await self._coll.create_index(
            [("idempotency_key", 1)],
            unique=True,
            partialFilterExpression={"idempotency_key": {"$type": "string"}},
        )

    async def enqueue(
        self,
        kind: str,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 5,
        delay_s: float = 0.0,
    ) -> str:
        if not kind or len(kind) > 100:
            raise ValueError("kind must be 1-100 characters")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if idempotency_key is not None and not (1 <= len(idempotency_key) <= 200):
            raise ValueError("idempotency_key must be 1-200 characters")
        now = self._clock()
        digest = payload_digest(payload)
        doc: dict[str, Any] = {
            "_id": secrets.token_hex(12),
            "kind": kind,
            "payload": dict(payload),
            "payload_digest": digest,
            "status": "queued",
            "attempts": 0,
            "max_attempts": max_attempts,
            "run_at": now + timedelta(seconds=max(0.0, delay_s)),
            "created_at": now,
            "updated_at": now,
            "errors": [],
        }
        if idempotency_key is not None:
            doc["idempotency_key"] = idempotency_key
        try:
            await self._coll.insert_one(doc)
        except Exception as exc:
            if getattr(exc, "code", None) != _DUPLICATE_KEY or idempotency_key is None:
                raise
            existing = await self._coll.find_one(
                {"idempotency_key": idempotency_key}, {"_id": 1, "kind": 1, "payload_digest": 1}
            )
            if existing is None:  # pragma: no cover - deleted between insert and read
                raise
            if existing.get("payload_digest") != digest or existing.get("kind") != kind:
                raise IdempotencyConflict("idempotency key reused with a different job") from exc
            return str(existing["_id"])
        return str(doc["_id"])

    async def claim(self, worker_id: str, kinds: list[str] | None = None) -> ClaimedJob | None:
        now = self._clock()
        flt: dict[str, Any] = {
            "$or": [
                {"status": "queued", "run_at": {"$lte": now}},
                {"status": "running", "lease_expires_at": {"$lt": now}},
            ]
        }
        if kinds:
            flt["kind"] = {"$in": list(kinds)}
        token = secrets.token_hex(16)
        doc = await self._coll.find_one_and_update(
            flt,
            {
                "$set": {
                    "status": "running",
                    "lease_token": token,
                    "lease_owner": worker_id,
                    "lease_expires_at": now + self._lease,
                    "started_at": now,
                    "updated_at": now,
                },
                "$inc": {"attempts": 1},
            },
            sort=[("run_at", 1)],
            return_document=True,
        )
        if doc is None:
            return None
        return ClaimedJob(
            id=str(doc["_id"]),
            kind=str(doc["kind"]),
            payload=dict(doc.get("payload") or {}),
            attempts=int(doc["attempts"]),
            max_attempts=int(doc["max_attempts"]),
            lease_token=token,
        )

    async def _fenced(self, job: ClaimedJob, update: dict[str, Any]) -> None:
        result = await self._coll.update_one(
            {"_id": job.id, "status": "running", "lease_token": job.lease_token}, update
        )
        if result.matched_count != 1:
            raise LeaseLost(f"lease on job {job.id} was lost")

    async def heartbeat(self, job: ClaimedJob) -> None:
        now = self._clock()
        await self._fenced(job, {"$set": {"lease_expires_at": now + self._lease, "updated_at": now}})

    async def complete(self, job: ClaimedJob, result: Mapping[str, Any] | None = None) -> None:
        now = self._clock()
        await self._fenced(
            job,
            {
                "$set": {"status": "succeeded", "result": dict(result or {}), "finished_at": now, "updated_at": now},
                "$unset": {"lease_token": "", "lease_expires_at": "", "lease_owner": ""},
            },
        )

    async def fail(self, job: ClaimedJob, error: BaseException | str, *, retryable: bool = True) -> str:
        """Record a failure; returns the new status (``queued`` or ``dead``)."""
        now = self._clock()
        entry = {"attempt": job.attempts, "at": now, "error": _error_text(error)}
        dead = not retryable or job.attempts >= job.max_attempts
        update: dict[str, Any] = {
            "$push": {"errors": {"$each": [entry], "$slice": -_MAX_ERROR_HISTORY}},
            "$unset": {"lease_token": "", "lease_expires_at": "", "lease_owner": ""},
        }
        if dead:
            update["$set"] = {
                "status": "dead",
                "dead_lettered_at": now,
                "updated_at": now,
                "last_error": entry["error"],
            }
        else:
            delay = self._retry.delay(job.attempts, self._rng)
            update["$set"] = {
                "status": "queued",
                "run_at": now + timedelta(seconds=delay),
                "updated_at": now,
                "last_error": entry["error"],
            }
        await self._fenced(job, update)
        if dead:
            log.warning("job %s (%s) dead-lettered after %d attempt(s)", job.id, job.kind, job.attempts)
        return "dead" if dead else "queued"

    async def redrive(self, job_id: str, *, extra_attempts: int = 1) -> bool:
        """Operator action: return a dead job to the queue with more attempts."""
        if extra_attempts < 1:
            raise ValueError("extra_attempts must be >= 1")
        now = self._clock()
        doc = await self._coll.find_one({"_id": job_id, "status": "dead"}, {"attempts": 1})
        if doc is None:
            return False
        result = await self._coll.update_one(
            {"_id": job_id, "status": "dead"},
            {
                "$set": {
                    "status": "queued",
                    "run_at": now,
                    "updated_at": now,
                    "max_attempts": int(doc["attempts"]) + extra_attempts,
                    "redriven_at": now,
                },
                "$unset": {"dead_lettered_at": ""},
            },
        )
        return result.modified_count == 1

    async def get(self, job_id: str) -> dict[str, Any] | None:
        doc = await self._coll.find_one({"_id": job_id}, {"payload": 0, "lease_token": 0})
        return dict(doc) if doc else None

    async def stats(self) -> dict[str, int]:
        counts = dict.fromkeys(STATUSES, 0)
        async for row in self._coll.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
            counts[str(row["_id"])] = int(row["n"])
        return counts

    async def dead_letters(self, limit: int = 50) -> list[dict[str, Any]]:
        cursor = (
            self._coll.find({"status": "dead"}, {"payload": 0, "lease_token": 0})
            .sort("dead_lettered_at", -1)
            .limit(max(1, min(limit, 500)))
        )
        return [dict(doc) async for doc in cursor]


class JobWorker:
    """Poll ``queue`` and run registered handlers with lease heartbeats."""

    def __init__(
        self,
        queue: JobQueue,
        handlers: Mapping[str, Handler],
        *,
        worker_id: str | None = None,
        heartbeat_s: float = 20.0,
        idle_sleep_s: float = 1.0,
    ) -> None:
        if not handlers:
            raise ValueError("at least one handler is required")
        self._queue = queue
        self._handlers = dict(handlers)
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(3)}"
        self._heartbeat_s = heartbeat_s
        self._idle_sleep_s = idle_sleep_s

    async def _beat(self, job: ClaimedJob) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_s)
            await self._queue.heartbeat(job)

    async def run_once(self) -> str | None:
        """Claim and run one job. Returns its resulting status, or None if idle."""
        job = await self._queue.claim(self.worker_id, list(self._handlers))
        if job is None:
            return None
        beat = asyncio.create_task(self._beat(job))
        try:
            result = await self._handlers[job.kind](job.payload)
        except NonRetryableError as exc:
            return await self._settle_failure(job, exc, retryable=False, beat=beat)
        except asyncio.CancelledError:
            beat.cancel()
            raise
        except Exception as exc:
            return await self._settle_failure(job, exc, retryable=True, beat=beat)
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
        try:
            await self._queue.complete(job, result)
        except LeaseLost:
            log.warning("job %s finished after its lease was taken over; result discarded", job.id)
            return "lease_lost"
        return "succeeded"

    async def _settle_failure(
        self, job: ClaimedJob, exc: BaseException, *, retryable: bool, beat: asyncio.Task[None]
    ) -> str:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError, LeaseLost):
            await beat
        try:
            return await self._queue.fail(job, exc, retryable=retryable)
        except LeaseLost:
            return "lease_lost"

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                status = await self.run_once()
            except Exception as exc:  # keep the worker alive across store blips
                log.warning("job worker %s poll failed: %s", self.worker_id, type(exc).__name__)
                status = None
            if status is None:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self._idle_sleep_s)


__all__ = [
    "ClaimedJob",
    "IdempotencyConflict",
    "JobQueue",
    "JobWorker",
    "LeaseLost",
    "NonRetryableError",
    "RetryPolicy",
    "payload_digest",
]
