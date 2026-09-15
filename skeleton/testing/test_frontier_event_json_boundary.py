from __future__ import annotations

import asyncio
import math

import pytest

from skeleton.frontier.events import DomainEvent, SQLiteEventJournal


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
def test_event_journal_rejects_non_finite_json_numbers_without_mutation(
    tmp_path,
    value: float,
):
    assert not math.isfinite(value)

    async def scenario():
        journal = SQLiteEventJournal(tmp_path / "strict-json.sqlite3")
        try:
            with pytest.raises(TypeError, match="JSON serializable"):
                await journal.journal(
                    DomainEvent.create(
                        "runtime.completed",
                        {"metrics": {"score": value}},
                    )
                )

            assert await journal.pending_count() == 0
            assert await journal.pending() == ()
        finally:
            journal.close()

    asyncio.run(scenario())


def test_event_journal_accepts_finite_nested_json_number(tmp_path):
    async def scenario():
        journal = SQLiteEventJournal(tmp_path / "finite-json.sqlite3")
        try:
            await journal.journal(
                DomainEvent.create(
                    "runtime.completed",
                    {"metrics": {"score": 1.25}},
                )
            )

            pending = await journal.pending()
            assert len(pending) == 1
            assert pending[0].event.payload == {"metrics": {"score": 1.25}}
        finally:
            journal.close()

    asyncio.run(scenario())
