"""Authenticated, bounded discovery of previous discourse job receipts.

Recovery must use Mongo account authority, not account-blind device storage.
Job listing never includes prompts, candidates, model output or JWT secrets.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routes import discourse


ALICE = {"tenant_id": "tenant1", "owner_id": "alice@example.test"}
BOB = {"tenant_id": "tenant1", "owner_id": "bob@example.test"}
OTHER_TENANT = {"tenant_id": "tenant2", "owner_id": "alice@example.test"}
ID_A = "a" * 32
ID_B = "b" * 32


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.sort_args = None
        self.limit_value = None

    def sort(self, *args):
        self.sort_args = args
        return self

    def limit(self, number):
        self.limit_value = number
        return self

    async def to_list(self, number):
        assert number == self.limit_value
        return self.rows[:number]


def test_unauthenticated_client_cannot_discover_private_job_receipts():
    app = FastAPI()
    app.include_router(discourse.router)
    with TestClient(app) as client:
        response = client.get("/api/discourse/jobs?limit=5")
    assert response.status_code == 401


def test_job_discovery_filters_exact_owner_and_leaks_no_private_fields(monkeypatch):
    calls = []

    class Jobs:
        def find(self, query, projection):
            calls.append((query, projection))
            # Simulate a compromised or incomplete projection adapter: even
            # overbroad data must be reconstructed from a tiny safe schema.
            return Cursor([{
                "job_id": ID_A, "status": "running",
                "created_at": "2026-11-06T12:00:00+00:00",
                "prompt": "PRIVATE-PROMPT",
                "candidates": [{"content": "PRIVATE-MODEL-OUTPUT"}],
                "tenant_id": "tenant1", "owner_id": "alice@example.test",
            }])

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    result = asyncio.run(discourse.list_jobs(5, identity=ALICE))
    assert result == {"jobs": [{
        "job_id": ID_A, "status": "running",
        "created_at": "2026-11-06T12:00:00+00:00",
        "worker_continuity_verified": False,
    }], "count": 1}
    assert calls[0][0] == ALICE
    assert calls[0][1] == {
        "_id": 0, "job_id": 1, "status": 1, "created_at": 1, "finished_at": 1,
    }
    assert "PRIVATE" not in str(result)
    assert "tenant_id" not in str(result)


def test_same_project_different_accounts_use_distinct_history_queries(monkeypatch):
    observed = []
    rows = [
        {"job_id": ID_A, "status": "done", "created_at": "2026-11-06T12:00:00Z", **ALICE},
        {"job_id": ID_B, "status": "error", "created_at": "2026-11-06T13:00:00Z", **BOB},
    ]

    class Jobs:
        def find(self, query, projection):
            observed.append(query)
            return Cursor([
                row for row in rows if row["tenant_id"] == query["tenant_id"]
                and row["owner_id"] == query["owner_id"]
            ])

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    alice = asyncio.run(discourse.list_jobs(identity=ALICE))
    bob = asyncio.run(discourse.list_jobs(identity=BOB))
    other = asyncio.run(discourse.list_jobs(identity=OTHER_TENANT))
    assert [row["job_id"] for row in alice["jobs"]] == [ID_A]
    assert [row["job_id"] for row in bob["jobs"]] == [ID_B]
    assert other["jobs"] == []
    assert observed == [ALICE, BOB, OTHER_TENANT]


@pytest.mark.parametrize("limit", [0, -1, 21, True, "5", 4.5, None])
def test_invalid_discovery_budgets_cannot_contact_database(monkeypatch, limit):
    class ForbiddenDatabase:
        @property
        def discourse_jobs(self):
            raise AssertionError("invalid limit reached the database")

    monkeypatch.setattr(discourse, "_db", ForbiddenDatabase())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discourse.list_jobs(limit, identity=ALICE))
    assert exc.value.status_code == 422


def test_database_outage_is_not_reported_as_empty_history(monkeypatch):
    class BrokenDB:
        @property
        def discourse_jobs(self):
            raise ConnectionError("storage outage")

    monkeypatch.setattr(discourse, "_db", BrokenDB())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discourse.list_jobs(identity=ALICE))
    assert exc.value.status_code == 503
    assert "storage outage" not in exc.value.detail


def test_corrupt_rows_are_discarded_not_exposed(monkeypatch):
    malformed = [
        None, 1, "not-json",
        {"job_id": "invalid", "status": "running", "created_at": "2026"},
        {"job_id": ID_A, "status": "completed_without_evidence", "created_at": "2026"},
        {"job_id": ID_A, "status": "done", "created_at": 42},
        {"job_id": ID_A, "status": "done", "created_at": "X" * 81},
    ]

    class Jobs:
        def find(self, *_args):
            return Cursor(malformed)

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    result = asyncio.run(discourse.list_jobs(limit=20, identity=ALICE))
    assert result == {"jobs": [], "count": 0}


def test_running_status_is_only_last_known_state_not_a_live_worker_claim(monkeypatch):
    class Jobs:
        def find(self, *_args):
            return Cursor([{
                "job_id": ID_B, "status": "running",
                "created_at": "2026-11-01T00:00:00Z",
            }])

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    result = asyncio.run(discourse.list_jobs(identity=ALICE))
    assert result["jobs"][0]["status"] == "running"
    assert result["jobs"][0]["worker_continuity_verified"] is False
