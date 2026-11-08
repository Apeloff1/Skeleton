"""Restart-safe *observation* evidence for paid discourse work.

An expired worker heartbeat cannot prove that a model operation failed or
succeeded, and must never trigger an implicit replay. Only the originally
admitted worker can publish a terminal job receipt with its run token.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from routes import discourse


ALICE = {"tenant_id": "tenant-A", "owner_id": "alice@example.test"}
NOW = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)
DID = "a" * 32
TOKEN = "f" * 32


def _running(**kw):
    return {
        "job_id": DID, "status": "running", "run_token": TOKEN,
        "created_at": (NOW - timedelta(minutes=5)).isoformat(),
        "heartbeat_at": (NOW - timedelta(seconds=30)).isoformat(),
        "tenant_id": ALICE["tenant_id"], "owner_id": ALICE["owner_id"],
        **kw,
    }


def test_fresh_owner_bound_heartbeat_reports_only_last_known_running_state():
    result = discourse._observed_job_state(_running(), now=NOW)
    assert result["status"] == "running"
    assert result["worker_continuity_verified"] is False
    assert "run_token" not in result
    assert "tenant_id" not in result
    assert "owner_id" not in result


def test_stale_worker_is_unconfirmed_not_complete_or_failed():
    row = _running()
    row["heartbeat_at"] = (NOW - timedelta(seconds=121)).isoformat()
    result = discourse._observed_job_state(row, now=NOW)
    assert result["status"] == "unconfirmed"
    assert result["error"] == "job_worker_continuity_unknown"
    assert row["status"] == "running"


@pytest.mark.parametrize("bad_timestamp", [
    None, "", "not-a-time", "2026-11-06T12:00:00",
    "2026-11-06T12:00:00+bad",
    "x" * 81,
    (NOW + timedelta(minutes=3)).isoformat(),
])
def test_malformed_or_impossibly_future_heartbeat_is_unconfirmed(bad_timestamp):
    row = _running()
    row["heartbeat_at"] = bad_timestamp
    # A missing timestamp uses the created_at field, which is also stale.
    assert discourse._observed_job_state(row, now=NOW)["status"] == "unconfirmed"


def test_terminal_receipt_stays_terminal_after_heartbeat_expiry():
    row = _running()
    row["status"] = "done"
    row["winner_model"] = "local:gguf"
    row["heartbeat_at"] = (NOW - timedelta(days=30)).isoformat()
    result = discourse._observed_job_state(row, now=NOW)
    assert result["status"] == "done"
    assert result["winner_model"] == "local:gguf"
    assert "run_token" not in result


def test_owned_get_result_never_exposes_run_token_and_marks_stale(monkeypatch):
    queries = []

    class Jobs:
        async def find_one(self, query, projection):
            queries.append((query, projection))
            row = _running()
            row["heartbeat_at"] = "2000-01-01T00:00:00+00:00"
            return row

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    result = asyncio.run(discourse.get_result(DID, identity=ALICE))
    assert result["status"] == "unconfirmed"
    assert result["error"] == "job_worker_continuity_unknown"
    assert "run_token" not in result
    assert queries[0][0] == {"job_id": DID, **ALICE}
    assert queries[0][1]["run_token"] == 0
    assert queries[0][1]["owner_id"] == 0
    assert queries[0][1]["tenant_id"] == 0


def test_heartbeat_cannot_write_outside_exact_scope_or_run_token(monkeypatch):
    seen = []
    stop = asyncio.Event()

    class Jobs:
        async def update_one(self, query, update, *, upsert):
            seen.append((query, update, upsert))
            stop.set()
            return SimpleNamespace(acknowledged=True, matched_count=1)

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    asyncio.run(discourse._renew_job_heartbeat(
        DID, ALICE, TOKEN, stop, interval_s=0.001,
    ))
    assert len(seen) == 1
    assert seen[0][0] == {
        "job_id": DID, **ALICE, "run_token": TOKEN, "status": "running",
    }
    assert isinstance(seen[0][1]["$set"]["heartbeat_at"], str)
    assert seen[0][2] is False


def test_heartbeat_on_unacknowledged_update_exits_without_forging_freshness(monkeypatch):
    seen = []

    class Jobs:
        async def update_one(self, query, update, *, upsert):
            seen.append(query)
            return SimpleNamespace(acknowledged=False, matched_count=0)

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    asyncio.run(discourse._renew_job_heartbeat(
        DID, ALICE, TOKEN, asyncio.Event(), interval_s=0.001,
    ))
    assert len(seen) == 1


def test_background_terminal_requires_same_run_token_and_status(monkeypatch):
    queries = []

    class Jobs:
        async def update_one(self, query, update, *, upsert):
            queries.append((query, update["$set"]["status"]))
            return SimpleNamespace(acknowledged=True, matched_count=1)

    async def complete(*_args, **_kwargs):
        return {"winner_model": "local:gguf", "winner_index": 0}

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    monkeypatch.setattr(discourse, "deliberate", complete)
    monkeypatch.setattr(discourse, "_ACTIVE_DELIBERATIONS", {DID})
    monkeypatch.setattr(discourse, "_ACTIVE_JOB_SCOPES", {
        DID: (ALICE["tenant_id"], ALICE["owner_id"]),
    })
    asyncio.run(discourse._run_bg(
        DID, discourse.DeliberateBody(prompt="Build original game"), ALICE, TOKEN,
    ))
    assert queries == [({
        "job_id": DID, **ALICE, "run_token": TOKEN, "status": "running",
    }, "done")]
    assert not discourse._ACTIVE_DELIBERATIONS
    assert not discourse._ACTIVE_JOB_SCOPES


def test_wrong_token_cannot_authorize_terminal_status(monkeypatch):
    queries = []

    class Jobs:
        async def update_one(self, query, update, *, upsert):
            queries.append(query)
            return SimpleNamespace(acknowledged=True, matched_count=0)

    async def complete(*_args, **_kwargs):
        return {"winner_model": "local:gguf"}

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    monkeypatch.setattr(discourse, "deliberate", complete)
    asyncio.run(discourse._run_bg(
        DID, discourse.DeliberateBody(prompt="Build original game"), ALICE, TOKEN,
    ))
    assert len(queries) == 2  # attempted done, then failed terminalization
    assert all(query["run_token"] == TOKEN for query in queries)
    assert all(query["status"] == "running" for query in queries)
