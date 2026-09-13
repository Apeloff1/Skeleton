import asyncio

import pytest

from core.durable_outbox import DurableOutbox, OutboxFullError, OutboxIntegrityError


def test_journal_is_durable_and_restores(tmp_path):
    outbox = DurableOutbox(tmp_path, cap=4)
    first = outbox.journal("builds", {"id": "a"})
    second = outbox.journal("deployments", {"id": "b"})
    assert first.seq == 1
    assert second.seq == 2
    assert outbox.pending_count == 2

    restored = DurableOutbox(tmp_path, cap=4)
    assert [entry.seq for entry in restored.pending()] == [1, 2]
    assert restored.pending()[0].payload == {"id": "a"}


def test_full_outbox_backpressures_without_evicting(tmp_path):
    outbox = DurableOutbox(tmp_path, cap=1)
    outbox.journal("builds", {"id": "a"})
    with pytest.raises(OutboxFullError, match="backpressured"):
        outbox.journal("builds", {"id": "b"})
    assert [entry.payload["id"] for entry in outbox.pending()] == ["a"]


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
        for value in range(3):
            outbox.journal("events", {"n": value})
        seen = []

        async def confirmer(entry):
            seen.append(entry.seq)
            return True

        assert await outbox.reconcile(confirmer, limit=2) == 2
        assert seen == [1, 2]
        assert [entry.seq for entry in outbox.pending()] == [3]
    asyncio.run(run())


def test_failed_reconciliation_keeps_failed_entries(tmp_path):
    async def run():
        outbox = DurableOutbox(tmp_path)
        outbox.journal("events", {"n": 1})
        outbox.journal("events", {"n": 2})
        count = await outbox.reconcile(lambda entry: entry.seq == 2)
        assert count == 1
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
    with pytest.raises(TypeError):
        outbox.journal("x", {"bad": object()})
    assert outbox.journal("x", {"ok": True}).seq == 1
