from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.frontier.events import EventBus, SQLiteEventJournal
from skeleton.frontier.logbook import (
    can_delete,
    log_entry_event,
    log_entry_from_record,
    log_entry_to_memory_item,
    log_statistics,
    milestone_entries,
    render_log_template,
    search_entries,
    timeline,
    toggle_pin,
)
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection


def _entry(**overrides):
    record = {
        "entry_id": "entry-1",
        "user_id": "user-1",
        "title": "New Waters Discovered",
        "content": "I've discovered Barnacle Bay.",
        "log_type": "discovery",
        "importance": "milestone",
        "location": "barnacle_bay",
        "related_entities": ["barnacle_bay"],
        "tags": ["exploration", "coastal"],
        "created_at": "2026-09-15T10:00:00+00:00",
        "is_auto_generated": False,
        "is_pinned": False,
    }
    record.update(overrides)
    return log_entry_from_record(record)


def test_log_entry_adapter_normalizes_source_shape():
    entry = _entry()

    assert entry.entry_id == "entry-1"
    assert entry.log_type == "discovery"
    assert entry.importance == "milestone"
    assert entry.tags == ("exploration", "coastal")
    assert entry.created_at == datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    assert entry.as_dict()["location"] == "barnacle_bay"


def test_auto_log_template_rendering_injects_clock_and_identity():
    template = {
        "title": "New Quest: {quest_name}",
        "template": "I've accepted {quest_name}. {quest_description}",
        "type": "quest",
        "importance": "normal",
    }
    fixed = datetime(2026, 9, 15, 11, 0, tzinfo=timezone.utc)

    entry = render_log_template(
        template,
        user_id="user-7",
        variables={"quest_name": "First Cast", "quest_description": "Catch a fish."},
        now=lambda: fixed,
        id_factory=lambda: "log-7",
    )

    assert entry.entry_id == "log-7"
    assert entry.title == "New Quest: First Cast"
    assert "Catch a fish" in entry.content
    assert entry.related_entities == ("quest_name", "quest_description")
    assert entry.is_auto_generated
    assert not can_delete(entry)


def test_auto_log_template_fails_closed_for_missing_variables_and_naive_clock():
    template = {
        "title": "Met {npc_name}",
        "template": "Met {npc_name}: {first_impression}",
        "type": "npc",
    }
    with pytest.raises(KeyError, match="first_impression"):
        render_log_template(
            template,
            user_id="u1",
            variables={"npc_name": "Barnacle Bill"},
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        render_log_template(
            template,
            user_id="u1",
            variables={"npc_name": "Bill", "first_impression": "Wise."},
            now=lambda: datetime(2026, 9, 15, 11, 0),
            id_factory=lambda: "id-1",
        )


def test_logbook_projection_search_milestones_stats_and_timeline():
    entries = [
        _entry(),
        _entry(
            entry_id="entry-2",
            title="Ordinary Trade",
            content="Sold fish at Port Prosperity.",
            log_type="trade",
            importance="normal",
            tags=["merchant"],
            created_at="2026-09-16T08:00:00+00:00",
        ),
        _entry(
            entry_id="entry-3",
            title="Legendary Catch!",
            content="Caught the thunder leviathan.",
            log_type="catch",
            importance="legendary",
            tags=["leviathan"],
            created_at="2026-10-01T08:00:00+00:00",
        ),
    ]

    assert [entry.entry_id for entry in search_entries(entries, "merchant")] == [
        "entry-2"
    ]
    assert [entry.entry_id for entry in milestone_entries(entries)] == [
        "entry-1",
        "entry-3",
    ]
    assert log_statistics(entries, known_types=["discovery", "trade", "catch"]) == {
        "total_entries": 3,
        "by_type": {"discovery": 1, "trade": 1, "catch": 1},
        "milestones": 1,
        "legendary_moments": 1,
    }
    september = timeline(entries, year=2026, month=9)
    assert list(september) == ["2026-09-15", "2026-09-16"]


def test_pin_toggle_and_delete_policy_are_pure():
    entry = _entry()
    pinned = toggle_pin(entry)
    assert pinned.is_pinned
    assert not entry.is_pinned
    assert can_delete(entry)
    assert not can_delete(_entry(is_auto_generated=True))


@pytest.mark.asyncio
async def test_log_entry_consumes_existing_memory_and_event_boundaries(tmp_path):
    entry = _entry()
    collection = SQLiteCollection(tmp_path / "log-memory.sqlite3", namespace="captains-log")
    journal = SQLiteEventJournal(tmp_path / "log-events.sqlite3", namespace="captains-log")
    try:
        memory = CollectionMemoryAdapter(collection)
        await memory.put(log_entry_to_memory_item(entry))
        hits = await memory.search(
            "Barnacle Bay",
            filters={"user_id": "user-1", "log_type": "discovery"},
        )
        assert [hit["id"] for hit in hits] == ["entry-1"]

        bus = EventBus(journal=journal)
        seen = []

        async def capture(event):
            seen.append((event.topic, event.payload["entry_id"]))

        await bus.subscribe("captains_log.created", capture)
        assert await bus.publish(log_entry_event(entry)) == 1
        assert seen == [("captains_log.created", "entry-1")]
        assert await journal.pending_count() == 0
    finally:
        collection.close()
        journal.close()
