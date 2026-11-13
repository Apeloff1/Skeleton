"""Crawler write binding and custody under executor acknowledgement failures.

No transport or model runs: the orphaned callable must stop at its submission
gate, and fake durable records expose whether capacity was released too early.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import threading
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import pytest

from core import dragon_crawler as crawler
from core.engine_client import EngineAuthorizationError

SCOPE = {"tenant_id": "crawler-test", "owner_id": "a" * 64}
SESSION = "crawler-custody-test"
BODY = {"expected_version": 1, "idempotency_key": "custody-attempt", "max_steps": 1}


def _value(row, path):
    for part in path.split("."):
        if not isinstance(row, dict) or part not in row:
            return None
        row = row[part]
    return row


def _matches(row, query):
    for key, expected in query.items():
        actual = _value(row, key)
        if isinstance(expected, dict) and "$nin" in expected:
            if actual in expected["$nin"]:
                return False
        elif actual != expected:
            return False
    return True


def _assign(row, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        row = row.setdefault(part, {})
    row[parts[-1]] = deepcopy(value)


class _Sessions:
    def __init__(self):
        self.row = {
            "_id": SESSION,
            **SCOPE,
            "version": 1,
            "status": "queued",
            "worker_epoch": 0,
            "consent_expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "snapshot": {},
            "operations": {},
        }
        self.defer_claim = False
        self.pending_claim = None

    async def update_one(self, query, update):
        if self.defer_claim and update.get("$set", {}).get("status") == "running":
            self.defer_claim = False
            self.pending_claim = (deepcopy(query), deepcopy(update))
            raise asyncio.CancelledError()
        if not _matches(self.row, query):
            return SimpleNamespace(matched_count=0, modified_count=0)
        for key, value in update.get("$set", {}).items():
            _assign(self.row, key, value)
        for key, value in update.get("$inc", {}).items():
            _assign(self.row, key, (_value(self.row, key) or 0) + value)
        for key in update.get("$unset", {}):
            target = self.row
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.get(part, {})
            target.pop(parts[-1], None)
        return SimpleNamespace(matched_count=1, modified_count=1)


class _Limits:
    def __init__(self):
        self.released = []

    async def find_one(self, query, projection):
        return None

    async def find_one_and_update(self, query, update, **kwargs):
        return {"_id": query["_id"], **update["$set"]}

    async def update_one(self, query, update, **kwargs):
        return SimpleNamespace(matched_count=1, modified_count=1)

    async def update_many(self, query, update):
        self.released.append(query["worker_token"])
        return SimpleNamespace(matched_count=2, modified_count=2)


def _application():
    app = object.__new__(crawler.DragonCrawlerApplication)
    app.sessions, app.limits, app._workers = _Sessions(), _Limits(), {}

    async def owned(scope, identifier):
        assert scope == SCOPE and identifier == SESSION
        return deepcopy(app.sessions.row)

    async def reconcile(scope, row):
        return row

    app._owned, app._reconcile = owned, reconcile
    return app


@pytest.mark.asyncio
async def test_enqueued_submission_failure_holds_custody_until_rejected_runner_drains(monkeypatch):
    app, queued = _application(), []
    loop = asyncio.get_running_loop()

    def enqueue_then_raise(executor, callback):
        queued.append(callback)
        raise RuntimeError("thread start failed after queue insertion")

    def forbidden_crawl_body():
        pytest.fail("an unacknowledged submission entered the crawler")

    monkeypatch.setattr(loop, "run_in_executor", enqueue_then_raise)
    monkeypatch.setattr(crawler, "_core", forbidden_crawl_body)
    with pytest.raises(crawler.CrawlerError) as caught:
        await app.run(SCOPE, SESSION, dict(BODY))
    assert caught.value.code == "crawler_dispatch_uncertain"
    assert caught.value.status == 503
    token, (_, custody) = next(iter(app._workers.items()))
    assert not custody.done()
    assert app.sessions.row["worker_token"] == token
    assert app.sessions.row["last_worker_exit_confirmed"] is False
    assert app.sessions.row["status"] == "interrupted"
    assert app.limits.released == []

    # The real executor may call its orphaned queued item much later. It must
    # observe the rejected gate, drain, and only then discharge its exact token.
    physical = threading.Thread(target=queued[0])
    physical.start()
    physical.join(timeout=2)
    assert not physical.is_alive()
    with pytest.raises(crawler.CrawlerError):
        await asyncio.wait_for(asyncio.shield(custody), timeout=2)
    async with asyncio.timeout(2):
        while app._workers:
            await asyncio.sleep(0)
    assert app.limits.released == [token]
    assert "worker_token" not in app.sessions.row
    assert app.sessions.row["last_worker_exit_confirmed"] is True


@pytest.mark.asyncio
async def test_executor_rejection_without_runner_entry_does_not_invent_exit(monkeypatch):
    app = _application()
    loop = asyncio.get_running_loop()

    def reject_queued_item(executor, callback):
        future = loop.create_future()
        future.set_exception(RuntimeError("pool initializer failed"))
        return future

    async def get(scope, identifier):
        return deepcopy(app.sessions.row)

    app.get = get
    monkeypatch.setattr(loop, "run_in_executor", reject_queued_item)
    result = await asyncio.wait_for(app.run(SCOPE, SESSION, dict(BODY)), timeout=2)
    assert result["ok"] is False
    assert result["run"]["error_code"] == "crawler_dispatch_uncertain"
    assert app.limits.released == []
    assert app.sessions.row["last_worker_exit_confirmed"] is False
    assert len(app._workers) == 1
    assert not next(iter(app._workers.values()))[1].done()


@pytest.mark.asyncio
async def test_cancelled_claim_fences_late_mongo_completion():
    app = _application()
    app.sessions.defer_claim = True
    with pytest.raises(asyncio.CancelledError):
        await app.run(SCOPE, SESSION, dict(BODY))
    assert app.sessions.row["status"] == "interrupted"
    assert app.sessions.row["last_worker_exit_confirmed"] is True
    assert len(app.limits.released) == 1
    late = await app.sessions.update_one(*app.sessions.pending_claim)
    assert late.modified_count == 0
    assert app.sessions.row["status"] == "interrupted"
    assert app._workers == {}


@pytest.mark.asyncio
async def test_acknowledged_runner_keeps_checkpoint_and_drains_before_release(monkeypatch):
    app = _application()
    original_update = app.sessions.update_one
    authorizations = []

    async def update(query, changes):
        # Lease expiry is covered by the canonical authority tests. This fake
        # exercises real thread-to-loop checkpoint and custody handoffs.
        return await original_update({key: value for key, value in query.items() if key != "$expr"}, changes)

    async def live(scope, identifier, token, epoch, **kwargs):
        current = app.sessions.row
        assert (scope, identifier) == (SCOPE, SESSION)
        assert (current["worker_token"], current["worker_epoch"]) == (token, epoch)
        authorizations.append(bool(kwargs.get("network_margin")))
        return deepcopy(current)

    async def admit(scope, identifier, snapshot):
        return {"fixture": "admitted"}

    async def get(scope, identifier):
        return deepcopy(app.sessions.row)

    class Runtime:
        @classmethod
        def from_snapshot(cls, snapshot):
            return cls()

        def run_slice(self, *, authorize, cancelled, on_checkpoint, **kwargs):
            authorize()
            assert not cancelled()
            on_checkpoint(self.snapshot(), {"sequence": 1, "event_digest": "b" * 64})
            return {"state": "completed", "sequence": 1, "slice_events": []}

        def snapshot(self):
            return {"fixture": "accepted checkpoint"}

        def status(self):
            return {"state": "completed"}

    app.sessions.update_one = update
    app._live, app._admit, app.get = live, admit, get
    monkeypatch.setattr(crawler, "_core", lambda: (None, Runtime))
    result = await asyncio.wait_for(app.run(SCOPE, SESSION, dict(BODY)), timeout=2)
    assert result["ok"] is True
    assert result["run"]["state"] == "completed"
    assert result["session"]["snapshot"] == {"fixture": "accepted checkpoint"}
    assert result["session"]["last_worker_exit_confirmed"] is True
    assert "worker_token" not in result["session"]
    assert authorizations[0] is True
    assert len(app.limits.released) == 1
    assert app._workers == {}


class _Engine:
    config = SimpleNamespace(service_principal="crawler-test-attester")

    def __init__(self, mutation=None, denied=False):
        self.mutation, self.denied = mutation, denied

    async def admit_storage_write(self, **write):
        if self.denied:
            raise EngineAuthorizationError("grant denied")
        operation = str(
            uuid5(
                NAMESPACE_URL,
                "\x1f".join(
                    (
                        "skeleton-external-storage",
                        self.config.service_principal,
                        write["tenant_id"],
                        write["capability"],
                        write["resource_id"],
                        write["write_id"],
                    )
                ),
            )
        )
        receipt = {
            "schema_version": 1,
            "operation_id": operation,
            "receipt_id": "storage-admission:" + hashlib.sha256(operation.encode()).hexdigest(),
            **write,
            "admitted_at": "2000-01-01T00:00:00+00:00",
            "quota_reservation_id": None,
            "admission_decision_id": None,
            "replayed": True,
        }
        if self.mutation:
            receipt.update(self.mutation(receipt))
        return receipt


@pytest.mark.asyncio
async def test_exact_admission_replay_accepts_original_timestamp():
    app = _application()
    app.engine = _Engine()
    receipt = await app._admit(SCOPE, SESSION, {"captured": "bounded fixture"})
    assert receipt["replayed"] is True
    assert receipt["admitted_at"] == "2000-01-01T00:00:00+00:00"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        lambda receipt: {"tenant_id": "another-tenant"},
        lambda receipt: {"capability": "another-capability"},
        lambda receipt: {"resource_id": "another-session"},
        lambda receipt: {"write_id": "another-write"},
        lambda receipt: {"storage_bytes": receipt["storage_bytes"] + 1},
        lambda receipt: {"storage_bytes": True},
        lambda receipt: {"schema_version": True},
        lambda receipt: {"replayed": 1},
        lambda receipt: {"operation_id": "00000000-0000-0000-0000-000000000000"},
        lambda receipt: {"receipt_id": "storage-admission:" + "0" * 64},
        lambda receipt: {"admitted_at": "2026-01-01T00:00:00"},
        lambda receipt: {"unexpected_authority": True},
    ],
)
async def test_mismatched_or_ambiguous_admission_fails_closed(mutation):
    app = _application()
    app.engine = _Engine(mutation)
    with pytest.raises(crawler.CrawlerError) as caught:
        await app._admit(SCOPE, SESSION, {"captured": "bounded fixture"})
    assert caught.value.code == "crawler_admission_invalid"
    assert caught.value.status == 503


@pytest.mark.asyncio
async def test_scope_denial_keeps_original_capture_scope():
    app, scope = _application(), dict(SCOPE)
    app.engine = _Engine(denied=True)
    with pytest.raises(crawler.CrawlerError) as caught:
        await app._admit(scope, SESSION, {"captured": "bounded fixture"})
    assert caught.value.code == "crawler_admission_scope_denied"
    assert scope == SCOPE
