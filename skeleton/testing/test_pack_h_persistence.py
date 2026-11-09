"""Pack H persistence: migrations, durable tier, idempotency store, outbox, records."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from skeleton.persistence.pack_h import (
    ConsumerLedger,
    DomainEvent,
    DurableTier,
    IdempotencyStore,
    InvalidKey,
    Migration,
    MigrationDrift,
    Outbox,
    OutboxError,
    OutboxRelay,
    Outcome,
    RecordConflict,
    RecordNotFound,
    RecordStore,
    StaleWrite,
    WriteBehindQueue,
    connect,
    current_version,
    fingerprint,
    migrate,
    migrate_all,
    verify,
)


class Clock:
    def __init__(self, t: float = 1_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


# -- migrations ---------------------------------------------------------------

def test_migrate_all_is_idempotent(tmp_path):
    conn = connect(str(tmp_path / "h.db"))
    first = migrate_all(conn)
    assert first == {"durable_tier": [1, 2], "idempotency": [1], "outbox": [1, 2], "records": [1]}
    assert migrate_all(conn) == {"durable_tier": [], "idempotency": [], "outbox": [], "records": []}
    assert current_version(conn, "outbox") == 2


def test_migration_drift_fails_closed():
    conn = connect(":memory:")
    migrate(conn, "x", (Migration(1, "a", ("CREATE TABLE t1 (a INTEGER)",)),))
    with pytest.raises(MigrationDrift):
        migrate(conn, "x", (Migration(1, "a", ("CREATE TABLE t1 (b INTEGER)",)),))
    with pytest.raises(MigrationDrift):
        verify(conn, "x", (Migration(1, "a", ("CREATE TABLE t1 (b INTEGER)",)),))


# -- durable tier ---------------------------------------------------------------

def test_durable_tier_ttl_versions_and_cas():
    clock = Clock()
    tier = DurableTier(clock=clock)
    tier.put("k", {"a": 1}, ttl_s=10)
    v1 = tier.version_of("k")
    assert tier.get("k") == {"a": 1}
    with pytest.raises(StaleWrite):
        tier.put("k", {"a": 2}, expected_version=v1 + 5)
    tier.put("k", {"a": 2}, expected_version=v1, ttl_s=10)
    assert tier.version_of("k") == v1 + 1
    clock.t += 11
    assert tier.get("k") is None


def test_durable_tier_delete_tombstones_and_version_continues():
    tier = DurableTier()
    tier.put("k", "v1")
    v = tier.version_of("k")
    assert tier.delete("k") is True
    assert tier.get("k") is None
    tier.put("k", "v2")
    assert tier.version_of("k") > v


def test_durable_tier_rejects_unsafe_values():
    tier = DurableTier()
    with pytest.raises(Exception):
        tier.put("k", object())


def test_write_behind_coalesces_and_read_your_writes():
    tier = DurableTier()
    q = WriteBehindQueue(tier, batch_size=1000, flush_interval_s=3600)
    for i in range(5):
        q.put("k", i)
    assert q.pending("k") == 4
    assert tier.get("k") is None
    q.flush()
    assert tier.get("k") == 4
    q.delete("k")
    assert q.pending("k") is None
    q.close()
    assert tier.get("k") is None


# -- idempotency store -------------------------------------------------------------

def test_idempotency_lifecycle_replay_and_mismatch():
    clock = Clock()
    store = IdempotencyStore(clock=clock, ttl_s=100, lock_ttl_s=5)
    fp = fingerprint("POST", "/r", {"a": 1})
    started = store.begin("t:op", "key-00001", fp)
    assert started.outcome is Outcome.STARTED
    inflight = store.begin("t:op", "key-00001", fp)
    assert inflight.outcome is Outcome.IN_FLIGHT and inflight.retry_after_s == 5.0
    assert store.complete("t:op", "key-00001", started.owner, status_code=201, body=b'{"ok":1}',
                          headers={"Set-Cookie": "x", "content-type": "application/json"})
    replay = store.begin("t:op", "key-00001", fp)
    assert replay.outcome is Outcome.REPLAY
    assert replay.response.status_code == 201 and replay.response.json() == {"ok": 1}
    assert "set-cookie" not in replay.response.headers
    other = store.begin("t:op", "key-00001", fingerprint("POST", "/r", {"a": 2}))
    assert other.outcome is Outcome.MISMATCH
    # same key in another scope is independent
    assert store.begin("u:op", "key-00001", fp).outcome is Outcome.STARTED
    clock.t += 101
    assert store.purge_expired() == 2


def test_idempotency_lock_takeover_and_stale_owner_cannot_complete():
    clock = Clock()
    store = IdempotencyStore(clock=clock, ttl_s=100, lock_ttl_s=5)
    first = store.begin("s", "key-00002", "fp")
    clock.t += 6
    second = store.begin("s", "key-00002", "fp")
    assert second.outcome is Outcome.STARTED and second.owner != first.owner
    assert store.complete("s", "key-00002", first.owner, status_code=200, body=b"{}") is False
    assert store.complete("s", "key-00002", second.owner, status_code=200, body=b"{}") is True
    assert store.counters["takeovers"] == 1


def test_idempotency_abandon_allows_retry_and_key_validation():
    store = IdempotencyStore()
    a = store.begin("s", "key-00003", "fp")
    assert store.abandon("s", "key-00003", a.owner)
    assert store.begin("s", "key-00003", "fp").outcome is Outcome.STARTED
    for bad in ("short", "x" * 129, "has space!", ""):
        with pytest.raises(InvalidKey):
            store.begin("s", bad, "fp")


def test_idempotency_concurrent_begin_single_winner(tmp_path):
    store = IdempotencyStore(str(tmp_path / "i.db"))
    outcomes = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        outcomes.append(store.begin("s", "key-race-1", "fp").outcome)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert outcomes.count(Outcome.STARTED) == 1
    assert outcomes.count(Outcome.IN_FLIGHT) == 7


def test_fingerprint_is_order_independent_for_json():
    assert fingerprint("post", "/a", {"x": 1, "y": 2}) == fingerprint("POST", "/a", {"y": 2, "x": 1})
    assert fingerprint("POST", "/a", {"x": 1}) != fingerprint("POST", "/b", {"x": 1})


# -- outbox ------------------------------------------------------------------------

def _ev(i: int = 0, **kw) -> DomainEvent:
    return DomainEvent("pack_h.thing", f"id-{i}", "thing.created", {"i": i}, **kw)


def test_outbox_append_is_transactional_with_domain_write():
    ob = Outbox()
    conn = ob.connection
    conn.execute("CREATE TABLE dom (id INTEGER)")
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO dom VALUES (1)")
    ob.append(_ev(1))
    conn.execute("ROLLBACK")
    assert ob.counts()["ready"] == 0
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO dom VALUES (2)")
    ob.append(_ev(2))
    conn.execute("COMMIT")
    assert ob.counts()["ready"] == 1


def test_outbox_duplicate_event_id_ignored_and_validation():
    ob = Outbox()
    e = _ev(1, event_id="fixed")
    assert ob.append_now(e) is True
    assert ob.append_now(e) is False
    with pytest.raises(OutboxError):
        DomainEvent("Bad Type", "a", "x.y", {})
    with pytest.raises(OutboxError):
        DomainEvent("a", "a", "x.y", [1])  # type: ignore[arg-type]


def test_relay_delivers_in_order_and_retries_then_dead_letters():
    clock = Clock()
    ob = Outbox(clock=clock)
    for i in range(3):
        ob.append_now(_ev(i))
    seen = []
    fail = {"id-1"}

    def publish(rec):
        if rec.event.aggregate_id in fail:
            raise RuntimeError("broker down")
        seen.append(rec.event.aggregate_id)

    relay = OutboxRelay(ob, publish, max_attempts=3, backoff_s=1.0, max_backoff_s=10)
    assert relay.run_once() == 2
    assert seen == ["id-0", "id-2"]
    assert ob.counts() == {"ready": 0, "scheduled": 1, "delivered": 2, "dead": 0}
    clock.t += 1
    relay.run_once()  # attempt 2, backoff 2s
    clock.t += 2
    relay.run_once()  # attempt 3 -> dead
    assert ob.counts()["dead"] == 1 and relay.dead == 1
    fail.clear()
    assert ob.requeue_dead() == 1
    assert relay.run_once() == 1
    assert seen[-1] == "id-1"


def test_relay_lease_expiry_redelivers_and_consumer_dedupes():
    clock = Clock()
    ob = Outbox(clock=clock)
    ob.append_now(_ev(7))
    crashed = ob.claim("w1", lease_s=5)
    assert len(crashed) == 1
    assert ob.claim("w2") == []  # still leased
    clock.t += 6
    handled = []
    ledger = ConsumerLedger(ob, "projector")
    handler = ledger.handler(lambda r: handled.append(r.event.event_id))
    handler(crashed[0])  # w1 actually published before crashing
    relay = OutboxRelay(ob, handler, worker_id="w2")
    assert relay.run_once() == 1
    assert handled == [crashed[0].event.event_id]
    assert ob.mark_delivered("w1", crashed[0].seq) is False  # stale worker cannot ack


# -- records -----------------------------------------------------------------------

def test_records_crud_emits_events_atomically():
    rs = RecordStore()
    rec = rs.create("t1", "note", {"text": "hi"}, record_id="r1")
    assert rec.version == 1
    with pytest.raises(RecordConflict):
        rs.create("t1", "note", {}, record_id="r1")
    with pytest.raises(RecordConflict):
        rs.update("t1", "r1", {"text": "x"}, expected_version=9)
    rs.update("t1", "r1", {"text": "bye"}, expected_version=1)
    assert rs.get("t1", "r1").body == {"text": "bye"}
    assert [r.record_id for r in rs.list("t1")] == ["r1"]
    assert rs.list("t2") == []
    rs.delete("t1", "r1")
    with pytest.raises(RecordNotFound):
        rs.get("t1", "r1")
    types = [e.event_type for e in rs.outbox.events_for(RecordStore.AGGREGATE, "t1/r1")]
    assert types == ["record.created", "record.updated", "record.deleted"]


def test_records_failed_write_emits_no_event():
    rs = RecordStore()
    rs.create("t1", "note", {}, record_id="r1")
    before = rs.outbox.counts()["ready"]
    with pytest.raises(RecordConflict):
        rs.update("t1", "r1", {"a": 1}, expected_version=42)
    assert rs.outbox.counts()["ready"] == before


def test_records_persist_across_reopen(tmp_path):
    path = str(tmp_path / "r.db")
    rs = RecordStore(path)
    rs.create("t", "note", {"a": 1}, record_id="r")
    rs.close()
    rs2 = RecordStore(path)
    assert rs2.get("t", "r").body == {"a": 1}
    assert rs2.outbox.counts()["ready"] == 1


def test_connect_uses_wal(tmp_path):
    conn = connect(str(tmp_path / "w.db"))
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert isinstance(conn, sqlite3.Connection)
