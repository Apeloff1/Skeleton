from __future__ import annotations

import asyncio
import sqlite3

import pytest

from skeleton.frontier.events import (
    DomainEvent,
    EventBus,
    EventJournalCorruptionError,
    SQLiteEventJournal,
)


def _rewrite_row(database, token: str, *, field: str, value: str) -> None:
    statements = {
        "token": "UPDATE frontier_event_journal SET token = ? WHERE token = ?",
        "topic": "UPDATE frontier_event_journal SET topic = ? WHERE token = ?",
        "payload_json": (
            "UPDATE frontier_event_journal SET payload_json = ? WHERE token = ?"
        ),
    }
    with sqlite3.connect(database) as connection:
        connection.execute(statements[field], (value, token))
        connection.commit()


@pytest.mark.parametrize(
    "replacement",
    [
        "not-a-uuid",
        "00000000-0000-1000-8000-000000000000",
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa".upper(),
    ],
    ids=["invalid", "wrong-version", "non-canonical-case"],
)
def test_corrupt_event_token_blocks_replay_before_delivery(tmp_path, replacement: str):
    async def scenario():
        database = tmp_path / "token.sqlite3"
        journal = SQLiteEventJournal(database)
        try:
            token = await journal.journal(DomainEvent.create("runtime.completed", {"ok": True}))
        finally:
            journal.close()

        _rewrite_row(database, token, field="token", value=replacement)

        reopened = SQLiteEventJournal(database)
        try:
            bus = EventBus(journal=reopened)
            delivered = []

            async def capture(event):
                delivered.append(event)

            await bus.subscribe("runtime.completed", capture)
            with pytest.raises(EventJournalCorruptionError, match="canonical UUIDv4"):
                await bus.replay_pending()
            assert delivered == []
            assert await reopened.pending_count() == 1
        finally:
            reopened.close()

    asyncio.run(scenario())


def test_duplicate_event_payload_key_is_rejected_as_ambiguous(tmp_path):
    async def scenario():
        database = tmp_path / "duplicate-key.sqlite3"
        journal = SQLiteEventJournal(database)
        try:
            token = await journal.journal(
                DomainEvent.create("runtime.completed", {"state": "original"})
            )
        finally:
            journal.close()

        _rewrite_row(
            database,
            token,
            field="payload_json",
            value='{"state":"first","state":"second"}',
        )

        reopened = SQLiteEventJournal(database)
        try:
            with pytest.raises(EventJournalCorruptionError, match="duplicate object keys"):
                await reopened.pending()
            assert await reopened.pending_count() == 1
        finally:
            reopened.close()

    asyncio.run(scenario())


def test_persisted_topic_must_remain_canonical(tmp_path):
    async def scenario():
        database = tmp_path / "topic.sqlite3"
        journal = SQLiteEventJournal(database)
        try:
            token = await journal.journal(DomainEvent.create("runtime.completed", {"ok": True}))
        finally:
            journal.close()

        _rewrite_row(database, token, field="topic", value=" runtime.completed ")

        reopened = SQLiteEventJournal(database)
        try:
            with pytest.raises(EventJournalCorruptionError, match="normalized form"):
                await reopened.pending()
            assert await reopened.pending_count() == 1
        finally:
            reopened.close()

    asyncio.run(scenario())


def test_journal_rejects_noncanonical_topic_before_mutation(tmp_path):
    async def scenario():
        journal = SQLiteEventJournal(tmp_path / "write-topic.sqlite3")
        try:
            event = DomainEvent(
                topic=" runtime.completed ",
                payload={"ok": True},
                occurred_at=DomainEvent.create("clock", {}).occurred_at,
            )
            with pytest.raises(ValueError, match="topic must be normalized"):
                await journal.journal(event)
            assert await journal.pending_count() == 0
        finally:
            journal.close()

    asyncio.run(scenario())
