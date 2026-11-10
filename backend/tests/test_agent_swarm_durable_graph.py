"""Graph swarm worker-count and durable receipt regression contracts."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core import databases
from routes import agent_swarm as swarm


def test_full_thirty_two_workers_are_not_silently_truncated():
    foci = swarm._subtasks("Implement original platformer tools", 32)
    assert len(foci) == 32
    assert all(isinstance(focus, str) and focus for focus in foci)


@pytest.mark.parametrize("workers", [0, -1, 33, True, 3.5, "4"])
def test_subtask_worker_budget_rejects_invalid_types_and_values(workers):
    with pytest.raises(ValueError, match="worker count"):
        swarm._subtasks("Original platformer tools", workers)


def test_max_worker_count_matches_http_request_contract():
    assert swarm.SwarmReq(directive="Original platformer tools", workers=32).workers == 32


def _fake_worker_return(index, focus, project, run_id):
    return {
        "type": "Finding", "worker": index, "focus": focus,
        "node_id": f"{project}:{run_id}:worker:{index}",
        "run_id": run_id,
        "recalled": [], "persisted": True,
    }


def test_success_requires_confirmed_graph_merge(monkeypatch):
    written = []

    async def fake_worker(index, focus, project, run_id):
        return _fake_worker_return(index, focus, project, run_id)

    class Collection:
        async def update_one(self, key, update, *, upsert=False):
            written.append((key, update, upsert))
            return SimpleNamespace(acknowledged=True)

    monkeypatch.setattr(swarm, "_worker", fake_worker)
    monkeypatch.setattr(databases, "core_db", {"swarm_graph": Collection()})
    result = asyncio.run(swarm.run_swarm(swarm.SwarmReq(
        directive="Build game runtime", project="game1", workers=12
    )))
    assert result["ok"] is True
    assert result["status"] == "durable"
    assert result["merge"]["persisted"] is True
    assert len(result["workers"]) == 12
    assert result["merge"]["worker_count"] == 12
    assert len(written) == 1
    assert written[0][0]["_id"] == f"game1:{result['run_id']}:merge"


def test_worker_failure_blocks_success_and_merge_publication(monkeypatch):
    async def fake_worker(index, focus, project, run_id):
        if index == 1:
            raise RuntimeError("failed durable write")
        return _fake_worker_return(index, focus, project, run_id)

    monkeypatch.setattr(swarm, "_worker", fake_worker)
    result = asyncio.run(swarm.run_swarm(swarm.SwarmReq(
        directive="Build game runtime", workers=3
    )))
    assert result["ok"] is False
    assert result["status"] == "partial_failure"
    assert result["failed_workers"] == [1]
    assert result["persisted_workers"] == 2
    assert result["merge"] is None


def test_unacknowledged_merge_cannot_claim_success(monkeypatch):
    async def fake_worker(index, focus, project, run_id):
        return _fake_worker_return(index, focus, project, run_id)

    class Collection:
        async def update_one(self, *_args, **_kwargs):
            return SimpleNamespace(acknowledged=False)

    monkeypatch.setattr(swarm, "_worker", fake_worker)
    monkeypatch.setattr(databases, "core_db", {"swarm_graph": Collection()})
    result = asyncio.run(swarm.run_swarm(swarm.SwarmReq(
        directive="Build game runtime", workers=2
    )))
    assert result["ok"] is False
    assert result["status"] == "merge_not_durable"
    assert result["merge"] is None


def test_graph_read_outage_is_not_reported_as_empty_success(monkeypatch):
    class NoDatabase:
        def __getitem__(self, _key):
            raise ConnectionError("offline")

    monkeypatch.setattr(databases, "core_db", NoDatabase())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(swarm.swarm_graph("game1"))
    assert exc.value.status_code == 503


@pytest.mark.parametrize("limit", [0, -1, 101, True, 2.5])
def test_graph_history_rejects_unbounded_limits(limit):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(swarm.swarm_graph("game1", limit))
    assert exc.value.status_code == 422


def test_unbound_or_forged_worker_receipt_blocks_durable_merge(monkeypatch):
    async def fake_worker(index, focus, project, run_id):
        return {
            "worker": index,
            "run_id": "different-run",
            "node_id": f"{project}:{run_id}:worker:{index}",
            "focus": focus,
            "persisted": True,
        }

    monkeypatch.setattr(swarm, "_worker", fake_worker)
    result = asyncio.run(swarm.run_swarm(swarm.SwarmReq(
        directive="Build game runtime", workers=2
    )))
    assert result["ok"] is False
    assert result["failed_workers"] == [0, 1]
    assert result["merge"] is None
