import asyncio
import json

import pytest

from core.durable_outbox import DurableOutbox, OutboxFullError, OutboxIntegrityError


def test_journal_is_durable_and_restores(tmp_path):
    outbox = DurableOutbox(tmp_path, cap=4)
    first = outbox.journal("builds", {"id": "a"})
    second = outbox.journal("deployments", {"id": "b"})
    assert first.seq == 1 and second.seq == 2
    restored = DurableOutbox(tmp_path, cap=4)
    assert [entry.seq for entry in restored.pending()] == [1, 2]
    assert restored.capacity_remaining == 2


def test_two_instances_share_sequence_and_capacity_coherently(tmp_path):
    left = DurableOutbox(tmp_path, cap=3)
    right = DurableOutbox(tmp_path, cap=3)
    a = left.journal("events", {"side": "left"})
    b = right.journal("events", {"side": "right"})
    assert (a.seq, b.seq) == (1, 2)
    assert [item.seq for item in left.pending()] == [1, 2]
    assert [item.seq for item in right.pending()] == [1, 2]
    assert left.capacity_remaining == right.capacity_remaining == 1
    assert left.health()["cross_process_locking"] is True


def test_sequence_never_reuses_after_queue_drains_and_restart(tmp_path):
    async def run():
        outbox = DurableOutbox(tmp_path)
        first = outbox.journal("events", {"n": 1})
        assert await outbox.confirm_one(first.seq, lambda _: True) is True
        assert outbox.pending_count == 0
        restored = DurableOutbox(tmp_path)
        second = restored.journal("events", {"n": 2})
        assert second.seq == first.seq + 1
    asyncio.run(run())


def test_sequence_metadata_tamper_fails_closed(tmp_path):
    outbox = DurableOutbox(tmp_path)
    outbox.journal("events", {"n": 1})
    path = tmp_path / "outbox.meta.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["next_seq"] = 1
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(OutboxIntegrityError, match="checksum mismatch"):
        DurableOutbox(tmp_path)


def test_full_outbox_backpressures_without_evicting(tmp_path):
    outbox = DurableOutbox(tmp_path, cap=1)
    assert outbox.has_capacity() is True
    outbox.journal("builds", {"id": "a"})
    assert outbox.has_capacity() is False
    with pytest.raises(OutboxFullError, match="backpressured"):
        outbox.journal("builds", {"id": "b"})
    assert [entry.payload["id"] for entry in outbox.pending()] == ["a"]


def test_capacity_preflight_supports_batch_queries(tmp_path):
    outbox = DurableOutbox(tmp_path, cap=3)
    assert outbox.has_capacity(3) is True
    outbox.journal("x", {"id": 1})
    assert outbox.has_capacity(2) is True
    assert outbox.has_capacity(3) is False
    with pytest.raises(ValueError, match="negative"):
        outbox.has_capacity(-1)


def test_confirm_removes_only_after_success(tmp_path):
    async def run():
        outbox = DurableOutbox(tmp_path)
        entry = outbox.journal("builds", {"id": "a"})
        assert await outbox.confirm_one(entry.seq, lambda _: False) is False
        assert outbox.pending_count == 1
        assert await outbox.confirm_one(entry.seq, lambda _: True) is True
        assert outbox.pending_count == 0
    asyncio.run(run())


def test_async_confirmer_and_reconcile_limit(tmp_path):
    async def run():
        outbox = DurableOutbox(tmp_path)
        for value in range(3): outbox.journal("events", {"n": value})
        seen = []
        async def confirmer(entry):
            seen.append(entry.seq); return True
        assert await outbox.reconcile(confirmer, limit=2) == 2
        assert seen == [1, 2]
        assert [entry.seq for entry in outbox.pending()] == [3]
    asyncio.run(run())


def test_failed_reconciliation_keeps_failed_entries(tmp_path):
    async def run():
        outbox = DurableOutbox(tmp_path)
        outbox.journal("events", {"n": 1}); outbox.journal("events", {"n": 2})
        assert await outbox.reconcile(lambda entry: entry.seq == 2) == 1
        assert [entry.seq for entry in outbox.pending()] == [1]
    asyncio.run(run())


def test_corrupt_journal_fails_closed(tmp_path):
    (tmp_path / "outbox.jsonl").write_text("{bad-json}\n", encoding="utf-8")
    with pytest.raises(OutboxIntegrityError, match="unreadable"):
        DurableOutbox(tmp_path)


def test_duplicate_sequence_fails_closed(tmp_path):
    path = tmp_path / "outbox.jsonl"
    line = '{"seq":1,"collection":"x","payload":{},"journaled_at":"t","confirmed":false}\n'
    path.write_text(line + line, encoding="utf-8")
    with pytest.raises(OutboxIntegrityError, match="sequence"):
        DurableOutbox(tmp_path)


def test_nonserializable_payload_does_not_consume_sequence(tmp_path):
    outbox = DurableOutbox(tmp_path)
    with pytest.raises(TypeError): outbox.journal("x", {"bad": object()})
    assert outbox.journal("x", {"ok": True}).seq == 1
