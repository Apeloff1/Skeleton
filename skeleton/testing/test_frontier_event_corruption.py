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


_ROW_REWRITE_SQL = {
    "payload_json": "UPDATE frontier_event_journal SET payload_json = ? WHERE token = ?",
    "occurred_at": "UPDATE frontier_event_journal SET occurred_at = ? WHERE token = ?",
    "topic": "UPDATE frontier_event_journal SET topic = ? WHERE token = ?",
}


def _rewrite_pending_row(database, token: str, column: str, value: str) -> None:
    try:
        statement = _ROW_REWRITE_SQL[column]
    except KeyError as exc:
        raise ValueError(f"unsupported event journal test column: {column}") from exc
    with sqlite3.connect(database) as connection:
        connection.execute(statement, (value, token))
        connection.commit()


@pytest.mark.parametrize(
    ("payload_json", "message"),
    [
        ('{"score":NaN}', "valid strict JSON"),
        ('{"broken"', "valid strict JSON"),
        ('[1,2,3]', "JSON object"),
    ],
    ids=["non-finite", "malformed", "non-object"],
)
def test_corrupt_payload_stays_pending_and_replay_fails_closed(
    tmp_path,
    payload_json: str,
    message: str,
):
    async def scenario():
        database = tmp_path / "corrupt-payload.sqlite3"
        journal = SQLiteEventJournal(database)
        try:
            token = await journal.journal(DomainEvent.create("runtime.completed", {"ok": True}))
        finally:
            journal.close()

        _rewrite_pending_row(database, token, "payload_json", payload_json)

        reopened = SQLiteEventJournal(database)
        try:
            bus = EventBus(journal=reopened)
            delivered = []

            async def capture(event):
                delivered.append(event)

            await bus.subscribe("runtime.completed", capture)
            with pytest.raises(EventJournalCorruptionError, match=message):
                await bus.replay_pending()

            assert delivered == []
            assert await reopened.pending_count() == 1
        finally:
            reopened.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("occurred_at", "message"),
    [
        ("not-a-timestamp", "ISO-8601"),
        ("2026-09-15T12:00:00", "timezone-aware"),
    ],
    ids=["invalid", "naive"],
)
def test_corrupt_timestamp_stays_pending_and_replay_fails_closed(
    tmp_path,
    occurred_at: str,
    message: str,
):
    async def scenario():
        database = tmp_path / "corrupt-time.sqlite3"
        journal = SQLiteEventJournal(database)
        try:
            token = await journal.journal(DomainEvent.create("runtime.completed", {"ok": True}))
        finally:
            journal.close()

        _rewrite_pending_row(database, token, "occurred_at", occurred_at)

        reopened = SQLiteEventJournal(database)
        try:
            with pytest.raises(EventJournalCorruptionError, match=message):
                await reopened.pending()
            assert await reopened.pending_count() == 1
        finally:
            reopened.close()

    asyncio.run(scenario())


def test_empty_corrupt_topic_stays_pending(tmp_path):
    async def scenario():
        database = tmp_path / "corrupt-topic.sqlite3"
        journal = SQLiteEventJournal(database)
        try:
            token = await journal.journal(DomainEvent.create("runtime.completed", {"ok": True}))
        finally:
            journal.close()

        _rewrite_pending_row(database, token, "topic", "   ")

        reopened = SQLiteEventJournal(database)
        try:
            with pytest.raises(EventJournalCorruptionError, match="non-empty string"):
                await reopened.pending()
            assert await reopened.pending_count() == 1
        finally:
            reopened.close()

    asyncio.run(scenario())
