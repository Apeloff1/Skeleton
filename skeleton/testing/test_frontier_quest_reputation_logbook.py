from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.frontier.events import EventBus, SQLiteEventJournal
from skeleton.frontier.logbook import (
    log_entry_event,
    log_entry_to_memory_item,
    render_log_template,
)
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection
from skeleton.frontier.quests import (
    initialize_progress,
    quest_from_record,
    reward_plan,
    update_objective_progress,
)
from skeleton.frontier.reputation import apply_reputation_change, faction_from_record


@pytest.mark.asyncio
async def test_quest_completion_flows_through_reputation_log_memory_and_events(tmp_path):
    quest = quest_from_record(
        {
            "id": "ms_007",
            "name": "The Storm Warning",
            "type": "main_story",
            "description": "Help evacuate the docks.",
            "objectives": [
                {"type": "warn_npcs", "count": 5},
                {"type": "save_boats", "count": 3},
            ],
            "rewards": {
                "gold": 400,
                "xp": 600,
                "reputation": {"port_authority": 15},
            },
            "prerequisite": "ms_006",
            "giver": "harbor_master_jenkins",
        }
    )
    progress = initialize_progress(quest)
    progress = update_objective_progress(progress, "0", 5)
    progress = update_objective_progress(progress, "1", 3)
    assert progress.completed

    rewards = reward_plan(quest.rewards)
    assert rewards.increments == {"gold": 400, "xp": 600}
    assert rewards.signals["reputation"] == {"port_authority": 15}

    faction = faction_from_record(
        {
            "id": "port_authority",
            "name": "Port Authority",
            "benefits": {
                "friendly": ["reduced_fees", "fast_processing"],
                "honored": ["priority_docking", "permit_waivers"],
            },
            "allies": ["merchants", "fishermen_guild"],
            "enemies": ["pirates", "smugglers"],
        }
    )
    reputation = apply_reputation_change(faction, 490, 15)
    assert reputation.new_reputation == 505
    assert reputation.new_level.name == "Friendly"
    assert reputation.level_changed
    assert reputation.new_benefits == ("reduced_fees", "fast_processing")

    completed_at = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    log_entry = render_log_template(
        {
            "title": "Quest Complete: {quest_name}",
            "template": (
                "I've completed the quest '{quest_name}'! {completion_notes} "
                "Rewards: {rewards}"
            ),
            "type": "quest",
            "importance": "achievement",
        },
        user_id="captain-1",
        variables={
            "quest_name": quest.name,
            "completion_notes": "The docks are safe.",
            "rewards": dict(quest.rewards),
        },
        now=lambda: completed_at,
        id_factory=lambda: "log:ms_007:captain-1",
    )

    memory_collection = SQLiteCollection(
        tmp_path / "quest-log-memory.sqlite3",
        namespace="captain-1",
    )
    event_journal = SQLiteEventJournal(
        tmp_path / "quest-log-events.sqlite3",
        namespace="captain-1",
    )
    try:
        memory = CollectionMemoryAdapter(memory_collection)
        await memory.put(log_entry_to_memory_item(log_entry))
        hits = await memory.search(
            "Storm Warning",
            filters={"user_id": "captain-1", "log_type": "quest"},
        )
        assert [hit["id"] for hit in hits] == ["log:ms_007:captain-1"]

        bus = EventBus(journal=event_journal)
        delivered = []

        async def capture(event):
            delivered.append((event.topic, event.payload["entry_id"]))

        await bus.subscribe("captains_log.created", capture)
        assert await bus.publish(log_entry_event(log_entry)) == 1
        assert delivered == [("captains_log.created", "log:ms_007:captain-1")]
        assert await event_journal.pending_count() == 0
    finally:
        memory_collection.close()
        event_journal.close()
