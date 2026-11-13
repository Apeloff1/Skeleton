"""Tenant-fair async deliberation admission before any costly provider work."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routes import discourse


TENANT = "tenant-A"
ALICE = {"tenant_id": TENANT, "owner_id": "alice@example.test"}
BOB = {"tenant_id": TENANT, "owner_id": "bob@example.test"}
OTHER_TENANT = {"tenant_id": "tenant-B", "owner_id": "alice@example.test"}


@pytest.fixture(autouse=True)
def isolated_admission_registry(monkeypatch):
    monkeypatch.setattr(discourse, "_ACTIVE_DELIBERATIONS", set())
    monkeypatch.setattr(discourse, "_ACTIVE_JOB_SCOPES", {})

    async def authorized_panel(**kwargs):
        assert kwargs["tenant_id"] and kwargs["actor_id"]
        return object()

    monkeypatch.setattr(discourse, "tenant_panel", authorized_panel)


def _request():
    return discourse.DeliberateBody(
        task="creative", prompt="Design an original procedural game world",
        discord=False, rounds=1,
    )


def _reserve(identity: dict, count: int, *, start: int = 0):
    for number in range(start, start + count):
        job = f"{number:032x}"
        discourse._ACTIVE_DELIBERATIONS.add(job)
        discourse._ACTIVE_JOB_SCOPES[job] = (
            identity["tenant_id"], identity["owner_id"],
        )


def _deny_database(monkeypatch):
    class ForbiddenDatabase:
        @property
        def discourse_jobs(self):
            raise AssertionError("quota denial must happen before durable admission")
    monkeypatch.setattr(discourse, "_db", ForbiddenDatabase())


def test_one_account_cannot_consume_all_global_slots(monkeypatch):
    _reserve(ALICE, discourse.MAX_ASYNC_PER_OWNER)
    _deny_database(monkeypatch)
    before = set(discourse._ACTIVE_DELIBERATIONS)
    with pytest.raises(HTTPException) as e:
        asyncio.run(discourse.deliberate_async(_request(), identity=ALICE))
    assert e.value.status_code == 429
    assert "account" in e.value.detail
    assert discourse._ACTIVE_DELIBERATIONS == before
    assert len(discourse._ACTIVE_JOB_SCOPES) == discourse.MAX_ASYNC_PER_OWNER


def test_tenant_budget_fences_multiple_accounts(monkeypatch):
    for n in range(discourse.MAX_ASYNC_PER_TENANT):
        _reserve(
            {"tenant_id": TENANT, "owner_id": "actor-" + str(n)},
            1, start=n,
        )
    _deny_database(monkeypatch)
    with pytest.raises(HTTPException) as e:
        asyncio.run(discourse.deliberate_async(_request(), identity=BOB))
    assert e.value.status_code == 429
    assert "tenant" in e.value.detail
    assert len(discourse._ACTIVE_DELIBERATIONS) == discourse.MAX_ASYNC_PER_TENANT


def test_global_budget_still_fences_distinct_tenants(monkeypatch):
    for n in range(discourse.MAX_ASYNC_DELIBERATIONS):
        _reserve(
            {"tenant_id": "tenant-" + str(n), "owner_id": "actor-" + str(n)},
            1, start=n,
        )
    _deny_database(monkeypatch)
    with pytest.raises(HTTPException) as e:
        asyncio.run(discourse.deliberate_async(_request(), identity=OTHER_TENANT))
    assert e.value.status_code == 503
    assert "capacity" in e.value.detail


def test_storage_failure_releases_owning_scope_and_global_slot(monkeypatch):
    class FailedStore:
        async def insert_one(self, document):
            assert document["tenant_id"] == TENANT
            assert document["owner_id"] == ALICE["owner_id"]
            raise OSError("database unavailable")

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=FailedStore()))
    with pytest.raises(HTTPException) as e:
        asyncio.run(discourse.deliberate_async(_request(), identity=ALICE))
    assert e.value.status_code == 503
    assert discourse._ACTIVE_DELIBERATIONS == set()
    assert discourse._ACTIVE_JOB_SCOPES == {}


def test_successful_job_completion_reclaims_tenant_capacity(monkeypatch):
    seen = []

    class Store:
        async def insert_one(self, doc):
            seen.append(("start", doc["job_id"], doc["owner_id"]))
            return SimpleNamespace(acknowledged=True)
        async def update_one(self, query, update, *, upsert):
            seen.append(("finish", query["job_id"], query["owner_id"]))
            return SimpleNamespace(acknowledged=True, matched_count=1)

    async def complete(*_args, **_kwargs):
        return {"winner_model": "local:gguf", "winner_score": 80}

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Store()))
    monkeypatch.setattr(discourse, "deliberate", complete)

    async def scenario():
        accepted = await discourse.deliberate_async(_request(), identity=ALICE)
        for _ in range(20):
            if not discourse._ACTIVE_DELIBERATIONS:
                break
            await asyncio.sleep(0)
        return accepted

    accepted = asyncio.run(scenario())
    assert accepted["status"] == "running"
    assert len(seen) == 2
    assert [item[0] for item in seen] == ["start", "finish"]
    assert seen[0][1] == seen[1][1] == accepted["job_id"]
    assert discourse._ACTIVE_DELIBERATIONS == set()
    assert discourse._ACTIVE_JOB_SCOPES == {}


def test_failure_during_background_start_reclaims_slots(monkeypatch):
    class Store:
        async def insert_one(self, document):
            return SimpleNamespace(acknowledged=True)
        async def update_one(self, *_args, **_kwargs):
            return SimpleNamespace(acknowledged=True, matched_count=1)

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Store()))
    # The coroutine is created before create_task; the route must close and
    # discard it if the event loop refuses to start background work.
    monkeypatch.setattr(discourse.asyncio, "create_task",
                        lambda _coro: (_ for _ in ()).throw(RuntimeError("no task slots")))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discourse.deliberate_async(_request(), identity=ALICE))
    assert exc.value.status_code == 503
    assert discourse._ACTIVE_DELIBERATIONS == set()
    assert discourse._ACTIVE_JOB_SCOPES == {}


def test_other_tenant_does_not_share_owner_quota(monkeypatch):
    _reserve(ALICE, discourse.MAX_ASYNC_PER_OWNER)
    # Independent tenant should not inherit the first tenant's account limit.
    class Store:
        async def insert_one(self, row):
            return SimpleNamespace(acknowledged=False)

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Store()))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discourse.deliberate_async(_request(), identity=OTHER_TENANT))
    assert exc.value.status_code == 503
    assert len(discourse._ACTIVE_DELIBERATIONS) == discourse.MAX_ASYNC_PER_OWNER
    assert len(discourse._ACTIVE_JOB_SCOPES) == discourse.MAX_ASYNC_PER_OWNER
