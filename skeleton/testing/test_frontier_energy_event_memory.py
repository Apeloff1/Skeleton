from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.frontier.energy import EnergyState, consume_energy
from skeleton.frontier.energy_adapters import (
    energy_event,
    energy_event_to_memory_item,
    energy_identity,
    energy_state_digest,
    energy_state_memory_item,
)
from skeleton.frontier.events import DomainEvent, EventBus, SQLiteEventJournal
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection


T0 = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _state():
    return EnergyState(
        current_energy=80,
        max_energy=100,
        last_updated=T0,
    )


def test_energy_event_binds_identity_and_full_state_digest():
    state = consume_energy(_state(), 5, now=T0)
    event = energy_event(
        state,
        subject_id="captain-1",
        action="spent",
        occurred_at=T0,
        delta=-5,
    )
    assert event.payload["energy_identity_sha256"] == energy_identity("captain-1")
    assert event.payload["energy_state_sha256"] == energy_state_digest(state)

    item = energy_event_to_memory_item(event)
    assert item["id"] == energy_identity("captain-1")
    assert item["metadata"]["delta"] == -5
    assert item["metadata"]["current_energy"] == 75


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("subject_id", "captain-2", "identity digest mismatch"),
        ("current_energy", 74, "state digest mismatch"),
        ("total_energy_spent", 999, "state digest mismatch"),
    ],
)
def test_energy_event_tampering_fails_closed(field, value, message):
    state = consume_energy(_state(), 5, now=T0)
    event = energy_event(
        state,
        subject_id="captain-1",
        action="spent",
        occurred_at=T0,
        delta=-5,
    )
    payload = dict(event.payload)
    payload[field] = value
    tampered = DomainEvent(
        topic=event.topic,
        payload=payload,
        occurred_at=event.occurred_at,
    )
    with pytest.raises(ValueError, match=message):
        energy_event_to_memory_item(tampered)


def test_energy_event_rejects_unsupported_action_and_temporal_reversal():
    state = _state()
    with pytest.raises(ValueError, match="unsupported energy action"):
        energy_event(
            state,
            subject_id="captain-1",
            action="deleted",
            occurred_at=T0,
        )
    with pytest.raises(ValueError, match="before state last_updated"):
        energy_event(
            state,
            subject_id="captain-1",
            action="spent",
            occurred_at=T0 - timedelta(seconds=1),
        )


def test_energy_state_memory_identity_is_stable_across_state_changes():
    before = _state()
    after = consume_energy(before, 10, now=T0)
    first = energy_state_memory_item(before, subject_id="captain-1")
    second = energy_state_memory_item(after, subject_id="captain-1")
    assert first["id"] == second["id"] == energy_identity("captain-1")
    assert first["metadata"]["energy_state_sha256"] != second["metadata"]["energy_state_sha256"]


def test_energy_transition_survives_journal_reopen_and_converges_in_memory(tmp_path):
    async def scenario():
        state = consume_energy(_state(), 10, now=T0)
        event = energy_event(
            state,
            subject_id="captain-1",
            action="spent",
            occurred_at=T0,
            delta=-10,
        )

        journal_path = tmp_path / "energy-events.sqlite3"
        journal = SQLiteEventJournal(journal_path, namespace="energy-events")
        try:
            bus = EventBus(journal=journal)
            assert await bus.publish(event) == 0
            assert await journal.pending_count() == 1
        finally:
            journal.close()

        memory_path = tmp_path / "energy-memory.sqlite3"
        reopened = SQLiteEventJournal(journal_path, namespace="energy-events")
        collection = SQLiteCollection(memory_path, namespace="energy-memory")
        try:
            memory = CollectionMemoryAdapter(collection)
            recovered = EventBus(journal=reopened)

            async def persist(replayed):
                await memory.put(energy_event_to_memory_item(replayed))

            await recovered.subscribe("energy.spent", persist)
            assert await recovered.replay_pending() == 1
            assert await reopened.pending_count() == 0

            # At-least-once repeat delivery converges through stable energy identity.
            await memory.put(energy_event_to_memory_item(event))
            assert collection.count() == 1
            hits = await memory.search(
                "energy spent",
                filters={"subject_id": "captain-1"},
            )
            assert len(hits) == 1
            assert hits[0]["metadata"]["current_energy"] == 70
        finally:
            reopened.close()
            collection.close()

    asyncio.run(scenario())
