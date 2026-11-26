"""Durable job queue against a real MongoDB (``MONGO_URL``; the Backend Test CI job provides one)."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from core.job_queue import (
    IdempotencyConflict,
    JobQueue,
    JobWorker,
    LeaseLost,
    NonRetryableError,
    RetryPolicy,
)

MONGO_URL = os.environ.get("MONGO_URL", "").strip()
pytestmark = pytest.mark.skipif(not MONGO_URL, reason="MONGO_URL not set; durable queue needs a real mongod")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def run(scenario: Callable[[Any, Clock], Awaitable[None]]) -> None:
    async def wrapper() -> None:
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        db = client[f"laneb_jobs_{uuid.uuid4().hex[:10]}"]
        try:
            await scenario(db, Clock())
        finally:
            await client.drop_database(db.name)
            client.close()

    asyncio.run(wrapper())


def make_queue(db: Any, clock: Clock, **kwargs: Any) -> JobQueue:
    return JobQueue(db, clock=clock, rng=lambda: 1.0, retry=RetryPolicy(base_delay_s=2, max_delay_s=10), **kwargs)


def test_enqueue_claim_complete_round_trip() -> None:
    async def scenario(db: Any, clock: Clock) -> None:
        q = make_queue(db, clock)
        await q.ensure_indexes()
        job_id = await q.enqueue("render", {"scene": 1})
        job = await q.claim("w1")
        assert job is not None and job.id == job_id and job.attempts == 1 and job.payload == {"scene": 1}
        assert await q.claim("w2") is None  # leased
        await q.complete(job, {"ok": True})
        doc = await q.get(job_id)
        assert doc is not None and doc["status"] == "succeeded" and doc["result"] == {"ok": True}
        assert "payload" not in doc and "lease_token" not in doc
        assert (await q.stats())["succeeded"] == 1

    run(scenario)


def test_idempotent_enqueue_and_conflict() -> None:
    async def scenario(db: Any, clock: Clock) -> None:
        q = make_queue(db, clock)
        await q.ensure_indexes()
        first = await q.enqueue("email", {"to": "a"}, idempotency_key="order-1")
        again = await q.enqueue("email", {"to": "a"}, idempotency_key="order-1")
        assert first == again
        with pytest.raises(IdempotencyConflict):
            await q.enqueue("email", {"to": "b"}, idempotency_key="order-1")
        # Jobs without keys never collide with each other.
        assert await q.enqueue("email", {"to": "a"}) != await q.enqueue("email", {"to": "a"})
        assert (await q.stats())["queued"] == 3

    run(scenario)


def test_retries_back_off_then_dead_letter_and_redrive() -> None:
    async def scenario(db: Any, clock: Clock) -> None:
        q = make_queue(db, clock)
        job_id = await q.enqueue("flaky", {"n": 1}, max_attempts=3)
        delays = []
        for attempt in (1, 2):
            job = await q.claim("w")
            assert job is not None and job.attempts == attempt
            assert await q.fail(job, RuntimeError(f"boom {attempt}")) == "queued"
            assert await q.claim("w") is None  # not due yet
            doc = await q.get(job_id)
            delays.append((doc["run_at"].replace(tzinfo=UTC) - clock.now).total_seconds())
            clock.advance(delays[-1])
        assert delays == [2.0, 4.0]  # exponential (jitter pinned to 1.0)
        job = await q.claim("w")
        assert job is not None and job.attempts == 3
        assert await q.fail(job, RuntimeError("final")) == "dead"
        dead = await q.dead_letters()
        assert [d["_id"] for d in dead] == [job_id]
        assert [e["error"] for e in dead[0]["errors"]] == [
            "RuntimeError: boom 1",
            "RuntimeError: boom 2",
            "RuntimeError: final",
        ]
        clock.advance(3600)
        assert await q.claim("w") is None  # dead jobs never run again on their own
        assert await q.redrive(job_id) is True
        job = await q.claim("w")
        assert job is not None and job.attempts == 4 and job.max_attempts == 4
        assert await q.redrive("missing") is False

    run(scenario)


def test_backoff_is_capped() -> None:
    policy = RetryPolicy(base_delay_s=2, max_delay_s=10)
    assert [policy.delay(n, lambda: 1.0) for n in (1, 2, 3, 4, 9)] == [2, 4, 8, 10, 10]
    assert policy.delay(5, lambda: 0.25) == 2.5


def test_expired_lease_is_recovered_and_stale_owner_is_fenced() -> None:
    async def scenario(db: Any, clock: Clock) -> None:
        q = make_queue(db, clock, lease_s=30)
        await q.enqueue("long", {})
        crashed = await q.claim("w-crashed")
        assert crashed is not None
        clock.advance(10)
        await q.heartbeat(crashed)  # extends to t+40
        clock.advance(25)
        assert await q.claim("w2") is None
        clock.advance(10)  # t+45: lease expired
        rescued = await q.claim("w2")
        assert rescued is not None and rescued.id == crashed.id and rescued.attempts == 2
        with pytest.raises(LeaseLost):
            await q.complete(crashed, {"late": True})
        with pytest.raises(LeaseLost):
            await q.fail(crashed, "late failure")
        await q.complete(rescued, {"ok": 1})
        assert (await q.get(rescued.id))["result"] == {"ok": 1}

    run(scenario)


def test_concurrent_claims_never_double_lease() -> None:
    async def scenario(db: Any, clock: Clock) -> None:
        q = make_queue(db, clock)
        await q.ensure_indexes()
        for n in range(20):
            await q.enqueue("bulk", {"n": n})
        claims = await asyncio.gather(*(q.claim(f"w{i}") for i in range(30)))
        got = [c.id for c in claims if c is not None]
        assert len(got) == 20 and len(set(got)) == 20

    run(scenario)


def test_worker_runs_handlers_retries_and_dead_letters_non_retryable() -> None:
    async def scenario(db: Any, clock: Clock) -> None:
        q = make_queue(db, clock)
        calls: list[str] = []

        async def ok(payload: dict[str, Any]) -> dict[str, Any]:
            calls.append(f"ok:{payload['n']}")
            return {"double": payload["n"] * 2}

        async def broken(payload: dict[str, Any]) -> None:
            calls.append("broken")
            raise NonRetryableError("bad input")

        async def transient(payload: dict[str, Any]) -> None:
            calls.append("transient")
            raise ConnectionError("try later")

        worker = JobWorker(q, {"ok": ok, "broken": broken, "transient": transient}, heartbeat_s=60)
        a = await q.enqueue("ok", {"n": 21})
        b = await q.enqueue("broken", {}, max_attempts=5)
        c = await q.enqueue("transient", {}, max_attempts=2)
        await q.enqueue("unhandled-kind", {})
        results = [await worker.run_once() for _ in range(3)]
        assert sorted(results) == ["dead", "queued", "succeeded"]
        assert await worker.run_once() is None  # transient not due; unhandled kind never claimed
        assert (await q.get(a))["result"] == {"double": 42}
        assert (await q.get(b))["status"] == "dead" and (await q.get(b))["attempts"] == 1
        clock.advance(60)
        assert await worker.run_once() == "dead"
        assert (await q.get(c))["last_error"] == "ConnectionError: try later"
        assert (await q.stats()) == {"queued": 1, "running": 0, "succeeded": 1, "dead": 2}

    run(scenario)


def test_enqueue_validates_arguments() -> None:
    async def scenario(db: Any, clock: Clock) -> None:
        q = make_queue(db, clock)
        for kwargs in ({"max_attempts": 0}, {"idempotency_key": ""}, {"idempotency_key": "k" * 201}):
            with pytest.raises(ValueError):
                await q.enqueue("x", {}, **kwargs)
        with pytest.raises(ValueError):
            await q.enqueue("", {})

    run(scenario)
