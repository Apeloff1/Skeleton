"""Historical event spine: restart, bounded capacity, chain and sink custody."""
import asyncio
import hashlib
import json
import sqlite3

import pytest

from zaibatsu.fabric import Fabric, ChainBroken
from zaibatsu.outbox import Outbox, OutboxFull, JournalIntegrityError


@pytest.mark.asyncio
async def test_restarts_preserve_sequence_chain_and_unconfirmed_records(tmp_path):
    path = tmp_path / "events.sqlite3"
    seen = {}
    async def sink(collection, document):
        seen.setdefault(document["_outbox_id"], (collection, document))
    first = Outbox(sink, path=path)
    fabric = Fabric(first, hot_cap=1)
    event = await fabric.append("build", "begin", {"x": [1]}, ["agent"])
    event.payload["x"].append(999)
    await first.journal("builds", {"id": "b"})
    second = Outbox(sink, path=path)
    recovered = Fabric(second, hot_cap=1)
    assert await second.pending_count() == 2
    assert recovered.head == event.hash
    third = await recovered.append("build", "end", {"x": 2}, ["agent"])
    assert third.seq == 2 and third.prev_hash == event.hash
    assert await recovered.verify()
    assert await second.reconcile() == 3
    assert await first.pending_count() == 0
    assert len(seen) == 3
    assert next(doc for _, doc in seen.values() if doc.get("id") == event.id)["payload"] == {"x": [1]}
    fresh = Outbox(sink, path=path)
    assert fresh.journaled_total == fresh.confirmed_total == 3
    assert fresh.health()["retained_records"] == 2
    assert await Fabric(fresh, hot_cap=1).verify()
    assert (await Fabric(fresh, hot_cap=1).tail("build"))[0].id == third.id


@pytest.mark.asyncio
async def test_backpressure_never_creates_ghost_fabric_sequence(tmp_path):
    async def sink(*_):
        return None
    outbox = Outbox(sink, cap=1, record_cap=2, path=tmp_path/"events.sqlite3")
    fabric = Fabric(outbox)
    first = await fabric.append("x", "start", {}, [])
    with pytest.raises(OutboxFull):
        await fabric.append("x", "lost", {}, [])
    assert fabric.head == first.hash
    await outbox.reconcile()
    second = await fabric.append("x", "end", {}, [])
    assert second.seq == 2
    await outbox.reconcile()
    with pytest.raises(OutboxFull):
        await fabric.append("x", "retention_full", {}, [])
    assert await fabric.verify()


@pytest.mark.asyncio
async def test_failed_sink_retains_stable_identity_and_retries(tmp_path, monkeypatch):
    import zaibatsu.outbox as module
    now = 100.0
    monkeypatch.setattr(module.time, "time", lambda: now)
    identities = []
    async def sink(collection, doc):
        identities.append(doc["_outbox_id"])
        return len(identities) > 1
    path = tmp_path/"events.sqlite3"
    box = Outbox(sink, path=path)
    await box.journal("events", {"ok": True})
    assert await box.reconcile() == 0
    assert await box.pending_count() == 1
    now += 10
    reopened = Outbox(sink, path=path)
    assert await reopened.reconcile() == 1
    assert identities[0] == identities[1]
    assert await reopened.pending_count() == 0


@pytest.mark.asyncio
async def test_two_reconcilers_cannot_claim_same_live_lease(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()
    async def sink(*_):
        entered.set()
        await release.wait()
    path = tmp_path/"events.sqlite3"
    a, b = Outbox(sink, path=path), Outbox(sink, path=path)
    await a.journal("events", {})
    task = asyncio.create_task(a.reconcile())
    await asyncio.wait_for(entered.wait(), 2)
    try:
        assert await b.reconcile() == 0
    finally:
        release.set()
    assert await task == 1
    assert await b.pending_count() == 0


@pytest.mark.asyncio
async def test_chain_detects_tampering_even_after_confirmation(tmp_path):
    async def sink(*_):
        pass
    path = tmp_path/"events.sqlite3"
    box = Outbox(sink, path=path)
    fabric = Fabric(box)
    await fabric.append("build", "start", {}, [])
    await box.reconcile()
    with sqlite3.connect(path) as db:
        body = db.execute("SELECT body FROM intents").fetchone()[0]
        doc = json.loads(body)
        doc["id"] = "00000000-0000-0000-0000-000000000000"
        forged = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        db.execute("UPDATE intents SET body=?,digest=?", (forged, hashlib.sha256(forged.encode()).hexdigest()))
    with pytest.raises(ChainBroken):
        await fabric.verify()
    with pytest.raises(JournalIntegrityError):
        Outbox(sink, path=path)


@pytest.mark.asyncio
async def test_rejects_nonfinite_and_reserved_values_without_admission(tmp_path):
    async def sink(*_):
        pass
    box = Outbox(sink, path=tmp_path/"events.sqlite3")
    with pytest.raises(ValueError):
        await box.journal("events", {"x": float("nan")})
    with pytest.raises(ValueError):
        await box.journal("events", {"_outbox_id": "forged"})
    with pytest.raises(ValueError):
        await box.journal("omega_fabric", {})
    assert box.journaled_total == 0
