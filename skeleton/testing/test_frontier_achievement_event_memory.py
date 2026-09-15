from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from skeleton.frontier.achievement_adapters import (
    achievement_event,
    achievement_event_to_memory_item,
    achievement_spec_digest,
    achievement_state_memory_item,
)
from skeleton.frontier.achievements import (
    AchievementState,
    achievement_from_record,
    claim_achievement,
    unlock_qualified,
    update_stat,
)
from skeleton.frontier.events import DomainEvent, EventBus, SQLiteEventJournal
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection


def _achievement():
    return achievement_from_record(
        {
            "id": "perfect_1",
            "name": "Perfect Timing",
            "description": "Get your first perfect catch",
            "category": "skill",
            "icon": "✨",
            "xp_reward": 75,
            "coin_reward": 150,
            "hidden": False,
            "requirement": {"type": "perfect_catches", "count": 1},
        }
    )


def test_achievement_unlock_survives_event_reopen_and_memory_upsert(tmp_path):
    async def scenario():
        achievement = _achievement()
        state = update_stat(AchievementState(), "perfect_catches", 1)
        state, unlocked = unlock_qualified((achievement,), state)
        assert [item.id for item in unlocked] == ["perfect_1"]

        occurred_at = datetime(2026, 9, 15, 11, 30, tzinfo=timezone.utc)
        event = achievement_event(
            achievement,
            subject_id="captain-1",
            action="unlocked",
            occurred_at=occurred_at,
        )
        assert event.payload["achievement_spec_sha256"] == achievement_spec_digest(
            achievement
        )

        journal_path = tmp_path / "achievement-events.sqlite3"
        journal = SQLiteEventJournal(journal_path, namespace="achievement-events")
        try:
            bus = EventBus(journal=journal)
            assert await bus.publish(event) == 0
            assert await journal.pending_count() == 1
        finally:
            journal.close()

        memory_path = tmp_path / "achievement-memory.sqlite3"
        reopened_journal = SQLiteEventJournal(
            journal_path,
            namespace="achievement-events",
        )
        collection = SQLiteCollection(memory_path, namespace="achievement-memory")
        try:
            memory = CollectionMemoryAdapter(collection)
            recovered = EventBus(journal=reopened_journal)

            async def persist(replayed):
                await memory.put(achievement_event_to_memory_item(replayed))

            await recovered.subscribe("achievement.unlocked", persist)
            assert await recovered.replay_pending() == 1
            assert await reopened_journal.pending_count() == 0

            # Repeat delivery converges to one record because event and state
            # projections share the stable subject+achievement identity.
            await memory.put(achievement_event_to_memory_item(event))
            assert collection.count() == 1

            hits = await memory.search(
                "Perfect Timing",
                filters={"subject_id": "captain-1", "achievement_id": "perfect_1"},
            )
            assert len(hits) == 1
            assert hits[0]["metadata"]["achievement_action"] == "unlocked"
            assert hits[0]["metadata"]["achievement_spec_sha256"] == event.payload[
                "achievement_spec_sha256"
            ]
        finally:
            reopened_journal.close()
            collection.close()

        # A state projection can intentionally replace the transition view with
        # current state while preserving the same stable memory identity.
        claimed_state, _ = claim_achievement(achievement, state)
        reopened_memory = SQLiteCollection(memory_path, namespace="achievement-memory")
        try:
            memory = CollectionMemoryAdapter(reopened_memory)
            state_item = achievement_state_memory_item(
                achievement,
                claimed_state,
                subject_id="captain-1",
            )
            await memory.put(state_item)
            assert reopened_memory.count() == 1
            hits = await memory.search(
                "achievement Perfect Timing",
                filters={"claimed": True},
            )
            assert [hit["id"] for hit in hits] == [state_item["id"]]
            assert hits[0]["metadata"]["achievement_spec_sha256"] == achievement_spec_digest(
                achievement
            )
        finally:
            reopened_memory.close()

    asyncio.run(scenario())


def test_achievement_event_identity_fails_closed_when_subject_is_tampered():
    achievement = _achievement()
    event = achievement_event(
        achievement,
        subject_id="captain-1",
        action="unlocked",
        occurred_at=datetime(2026, 9, 15, 11, 30, tzinfo=timezone.utc),
    )
    payload = dict(event.payload)
    payload["subject_id"] = "captain-2"
    tampered = DomainEvent(
        topic=event.topic,
        payload=payload,
        occurred_at=event.occurred_at,
    )

    with pytest.raises(ValueError, match="identity digest mismatch"):
        achievement_event_to_memory_item(tampered)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "Altered Name"),
        ("category", "altered-category"),
        ("hidden", True),
        ("requirement_type", "other_progress"),
        ("requirement_count", 99),
    ],
    ids=["name", "category", "hidden", "requirement-type", "requirement-count"],
)
def test_achievement_event_spec_digest_rejects_tampered_policy_fields(field, value):
    achievement = _achievement()
    event = achievement_event(
        achievement,
        subject_id="captain-1",
        action="unlocked",
        occurred_at=datetime(2026, 9, 15, 11, 30, tzinfo=timezone.utc),
    )
    payload = dict(event.payload)
    payload[field] = value
    tampered = DomainEvent(
        topic=event.topic,
        payload=payload,
        occurred_at=event.occurred_at,
    )

    with pytest.raises(ValueError, match="spec digest mismatch"):
        achievement_event_to_memory_item(tampered)


def test_achievement_event_rejects_invalid_transition_action():
    achievement = _achievement()
    with pytest.raises(ValueError, match="unsupported achievement action"):
        achievement_event(
            achievement,
            subject_id="captain-1",
            action="deleted",
            occurred_at=datetime(2026, 9, 15, 11, 30, tzinfo=timezone.utc),
        )


def test_achievement_state_memory_requires_unlock():
    with pytest.raises(ValueError, match="must be unlocked"):
        achievement_state_memory_item(
            _achievement(),
            AchievementState(),
            subject_id="captain-1",
        )
