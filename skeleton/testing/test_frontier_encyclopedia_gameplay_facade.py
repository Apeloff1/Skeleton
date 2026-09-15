from __future__ import annotations

from datetime import datetime, timezone

import skeleton.frontier.gameplay as gameplay


NOW = datetime(2026, 9, 15, 15, 30, tzinfo=timezone.utc)


def test_gameplay_facade_uses_canonical_collection_and_achievement_adapters():
    assert gameplay.FishCollectionState.__module__ == "skeleton.frontier.encyclopedia"
    assert gameplay.FishDiscoveryStats.__module__ == "skeleton.frontier.encyclopedia"
    assert gameplay.record_fish_catch.__module__ == "skeleton.frontier.encyclopedia"
    assert gameplay.encyclopedia_collection_event.__module__ == (
        "skeleton.frontier.encyclopedia_adapters"
    )
    assert gameplay.biotope_achievement_from_record.__module__ == (
        "skeleton.frontier.biotope_achievement_adapters"
    )


def test_gameplay_facade_composes_collection_event_memory_without_catalog():
    collection = gameplay.record_fish_catch(
        gameplay.empty_fish_collection(),
        fish_id="trout",
        size=42,
        occurred_at=NOW,
    ).collection
    event = gameplay.encyclopedia_collection_event(
        collection,
        subject_id="player-1",
        fish_id="trout",
        action="fish_discovered",
        occurred_at=NOW,
    )
    memory = gameplay.encyclopedia_event_to_memory_item(event)

    assert memory["metadata"]["unique_species_discovered"] == 1
    assert memory["metadata"]["total_fish_caught"] == 1
    assert memory["metadata"]["collection_state_sha256"] == (
        gameplay.encyclopedia_collection_digest(collection)
    )


def test_gameplay_facade_biotope_achievement_adapter_reuses_existing_engine_shape():
    spec = gameplay.biotope_achievement_from_record(
        {
            "id": "lake_beginner",
            "name": "Lake Angler",
            "biotope": "freshwater_lake",
            "category": "biotope",
            "requirement": {"type": "lake_catches", "count": 10},
            "rewards": {"xp": 100, "coins": 500},
        }
    )

    assert spec.__class__.__module__ == "skeleton.frontier.achievements"
    assert spec.requirement.kind == "lake_catches"
    assert spec.metadata["biotope"] == "freshwater_lake"
