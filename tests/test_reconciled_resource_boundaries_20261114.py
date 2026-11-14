"""Focused cross-component resource and protocol guard regressions."""
import asyncio

import pytest

from skeleton.frontier.runtime import memory_adapters
from skeleton.frontier.runtime.memory_adapters import SQLiteCollection
from skeleton.frontier.runtime.singleflight import SingleFlight
from skeleton.realtime.envelope import (
    EnvelopeError, RealtimeEvent, strict_frame_json, MAX_PAYLOAD_BYTES,
    validate_identifier, validate_type,
)
from skeleton.realtime.hub import RealtimeHub, RealtimeLimitError, sealed_principal_authorizer


@pytest.mark.parametrize("raw", [
    '{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}',
    '{"a":1e309}', '{"a":-1e309}', '{"a":[{"x":1e400}]}',
])
def test_ambiguous_frame_rejected(raw):
    with pytest.raises(EnvelopeError):
        strict_frame_json(raw)


def test_finite_frame_number_and_identifiers_are_accepted():
    assert strict_frame_json('{"a":1.25e2}') == {"a": 125.0}
    assert validate_identifier("job-1", "job_id") == "job-1"
    assert validate_type("build", "build.progress") == "build.progress"


def test_trailing_line_breaks_are_rejected_in_wire_fields():
    with pytest.raises(EnvelopeError):
        validate_identifier("job-1\n", "job_id")
    with pytest.raises(EnvelopeError):
        validate_type("build", "build.progress\n")
    with pytest.raises(EnvelopeError):
        RealtimeEvent("1\n", "2026-11-14T00:00:00Z", "build", "build.progress")


def test_snapshot_byte_budget_preserves_membership_and_subscription():
    hub = RealtimeHub(authorizer=sealed_principal_authorizer,
                      presence_scope_authorizer=lambda *_: True)
    with pytest.raises(RealtimeLimitError, match="snapshot byte capacity"):
        for index in range(100):
            hub.presence("join", client_id=f"client-{index}", principal="owner",
                         scope="scope", meta={"note": "x" * 1800})
    sub = hub.subscribe(["presence"], principal="owner")
    snapshot = sub.drain()[0]
    assert snapshot.payload["count"] == hub.stats()["presence_members"]
    assert len(snapshot.to_json().encode()) <= MAX_PAYLOAD_BYTES + 1024


def test_global_database_budget_rolls_back_across_namespaces(tmp_path, monkeypatch):
    monkeypatch.setattr(memory_adapters, "MAX_DATABASE_ROWS", 2)
    path = tmp_path / "memory.sqlite"
    with SQLiteCollection(path, namespace="one") as first, SQLiteCollection(path, namespace="two") as second:
        first.add(ids=["a"], documents=["x"], metadatas=[{}])
        with pytest.raises(OverflowError, match="database capacity"):
            second.add(ids=["b", "c"], documents=["y", "z"], metadatas=[{}, {}])
        assert first.count() == 1
        assert second.count() == 0


def test_top_k_retains_recent_tie_break_order():
    with SQLiteCollection() as memory:
        memory.add(ids=["a", "b", "c"], documents=["same"] * 3, metadatas=[{}] * 3)
        assert memory.query(query_texts=["same"], n_results=2)["ids"] == [["c", "b"]]


@pytest.mark.asyncio
async def test_shutdown_timeout_fences_cancellation_resistant_worker():
    flight = SingleFlight(shutdown_timeout=0.01)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def work():
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return {"ok": True}

    outer = asyncio.create_task(flight.run("key", "fingerprint", work))
    await entered.wait()
    try:
        with pytest.raises(TimeoutError):
            await flight.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            await flight.run("other", "other", work)
    finally:
        release.set()
        await outer
        await flight.aclose()
