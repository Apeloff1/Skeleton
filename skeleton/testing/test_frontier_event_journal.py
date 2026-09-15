from __future__ import annotations

import asyncio

import pytest

from skeleton.frontier.events import DomainEvent, EventBus, SQLiteEventJournal


def test_event_journal_confirms_after_successful_delivery(tmp_path):
    async def scenario():
        journal = SQLiteEventJournal(tmp_path / "events.sqlite3")
        try:
            bus = EventBus(journal=journal)
            observed_pending = []

            async def handler(event):
                observed_pending.append(await journal.pending_count())
                assert event.payload["value"] == 7

            await bus.subscribe("runtime.completed", handler)
            delivered = await bus.publish(
                DomainEvent.create("runtime.completed", {"value": 7})
            )

            assert delivered == 1
            assert observed_pending == [1]
            assert await journal.pending_count() == 0
        finally:
            journal.close()

    asyncio.run(scenario())


def test_event_journal_leaves_failed_delivery_pending_and_replays_after_reopen(tmp_path):
    async def scenario():
        database = tmp_path / "failed.sqlite3"
        journal = SQLiteEventJournal(database)
        try:
            bus = EventBus(journal=journal)

            async def failing_handler(event):
                raise RuntimeError(f"cannot deliver {event.topic}")

            await bus.subscribe("runtime.failed", failing_handler)
            with pytest.raises(RuntimeError, match="cannot deliver runtime.failed"):
                await bus.publish(
                    DomainEvent.create("runtime.failed", {"reason": "boom"})
                )

            pending = await journal.pending()
            assert len(pending) == 1
            assert pending[0].event.topic == "runtime.failed"
            assert pending[0].event.payload == {"reason": "boom"}
        finally:
            journal.close()

        reopened = SQLiteEventJournal(database)
        try:
            recovered = EventBus(journal=reopened)
            seen = []

            async def recovered_handler(event):
                seen.append((event.topic, event.payload["reason"]))

            await recovered.subscribe("runtime.failed", recovered_handler)
            assert await recovered.replay_pending() == 1
            assert seen == [("runtime.failed", "boom")]
            assert await reopened.pending_count() == 0
        finally:
            reopened.close()

    asyncio.run(scenario())


def test_event_journal_replay_preserves_order_and_stops_on_failure(tmp_path):
    async def scenario():
        journal = SQLiteEventJournal(tmp_path / "replay.sqlite3")
        try:
            await journal.journal(DomainEvent.create("ordered", {"seq": 1}))
            await journal.journal(DomainEvent.create("ordered", {"seq": 2}))
            await journal.journal(DomainEvent.create("ordered", {"seq": 3}))

            bus = EventBus(journal=journal)
            seen = []

            async def handler(event):
                seen.append(event.payload["seq"])
                if event.payload["seq"] == 2:
                    raise RuntimeError("stop at second")

            await bus.subscribe("ordered", handler)
            with pytest.raises(RuntimeError, match="stop at second"):
                await bus.replay_pending()

            assert seen == [1, 2]
            pending = await journal.pending()
            assert [entry.event.payload["seq"] for entry in pending] == [2, 3]
        finally:
            journal.close()

    asyncio.run(scenario())


def test_event_journal_backpressures_when_pending_capacity_is_full(tmp_path):
    async def scenario():
        journal = SQLiteEventJournal(tmp_path / "capacity.sqlite3", capacity=1)
        try:
            first = await journal.journal(DomainEvent.create("one", {"value": 1}))
            assert await journal.pending_count() == 1

            with pytest.raises(RuntimeError, match="backpressured, not dropped"):
                await journal.journal(DomainEvent.create("two", {"value": 2}))

            await journal.confirm(first)
            second = await journal.journal(DomainEvent.create("two", {"value": 2}))
            assert second
            assert await journal.pending_count() == 1
        finally:
            journal.close()

    asyncio.run(scenario())


def test_event_journal_rejects_non_json_payload(tmp_path):
    async def scenario():
        journal = SQLiteEventJournal(tmp_path / "json.sqlite3")
        try:
            event = DomainEvent.create("bad", {"value": object()})
            with pytest.raises(TypeError, match="JSON serializable"):
                await journal.journal(event)
            assert await journal.pending_count() == 0
        finally:
            journal.close()

    asyncio.run(scenario())
