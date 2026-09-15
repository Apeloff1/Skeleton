from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.frontier.encyclopedia import (
    FishCollectionState,
    FishDiscoveryStats,
    collection_completion_percent,
    collection_summary,
    empty_collection,
    project_fish_entry,
    rarity_catch_counts,
    record_fish_catch,
)


NOW = datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc)


def test_first_discovery_and_repeat_catch_update_canonical_stats():
    first = record_fish_catch(
        empty_collection(), fish_id="trout", size=40, occurred_at=NOW
    )
    second = record_fish_catch(
        first.collection,
        fish_id="trout",
        size=65,
        occurred_at=NOW + timedelta(minutes=5),
    )
    third = record_fish_catch(
        second.collection,
        fish_id="trout",
        size=25,
        occurred_at=NOW + timedelta(minutes=10),
    )

    assert first.is_new_discovery is True
    assert second.is_new_discovery is False
    assert third.stats.caught == 3
    assert third.stats.largest == 65
    assert third.stats.smallest == 25
    assert third.stats.first_caught == NOW
    assert third.collection.discovered_fish == frozenset({"trout"})


def test_out_of_order_replay_converges_on_earliest_first_caught():
    later = record_fish_catch(
        empty_collection(),
        fish_id="sturgeon",
        size=120,
        occurred_at=NOW + timedelta(hours=2),
    )
    earlier = record_fish_catch(
        later.collection,
        fish_id="sturgeon",
        size=110,
        occurred_at=NOW,
    )

    assert earlier.stats.first_caught == NOW
    assert earlier.stats.caught == 2
    assert earlier.stats.largest == 120
    assert earlier.stats.smallest == 110


def test_collection_rejects_discovery_stat_identity_drift():
    stats = FishDiscoveryStats(1, 40, 40, NOW)
    with pytest.raises(ValueError, match="exactly match"):
        FishCollectionState(
            discovered_fish=frozenset({"trout"}),
            fish_stats={"bass": stats},
        )


def test_collection_completion_uses_external_catalog_and_fails_closed():
    collection = record_fish_catch(
        empty_collection(), fish_id="trout", size=40, occurred_at=NOW
    ).collection

    assert collection_completion_percent(collection, ("trout", "bass")) == 50.0
    with pytest.raises(ValueError, match="absent from supplied catalog"):
        collection_completion_percent(collection, ("bass",))


def test_undiscovered_projection_masks_details_without_mutating_catalog():
    record = {
        "id": "leviathan",
        "name": "The Leviathan",
        "description": "Ancient guardian",
        "facts": ["Rare", "Large"],
        "discovery_level": 75,
        "rarity": "legendary",
    }

    hidden = project_fish_entry(record, empty_collection(), player_level=10)
    visible_name = project_fish_entry(record, empty_collection(), player_level=80)

    assert hidden["name"] == "???"
    assert hidden["description"] == "???"
    assert hidden["facts"] == []
    assert hidden["can_discover"] is False
    assert visible_name["name"] == "The Leviathan"
    assert visible_name["description"] == "???"
    assert visible_name["facts"] == []
    assert record["description"] == "Ancient guardian"
    assert record["facts"] == ["Rare", "Large"]


def test_discovered_projection_returns_json_safe_stats():
    collection = record_fish_catch(
        empty_collection(), fish_id="trout", size=42, occurred_at=NOW
    ).collection
    record = {
        "id": "trout",
        "name": "Rainbow Trout",
        "description": "A fish",
        "facts": ["Fact"],
        "discovery_level": 15,
    }

    projected = project_fish_entry(record, collection, player_level=15)
    assert projected["discovered"] is True
    assert projected["stats"] == {
        "caught": 1,
        "largest": 42.0,
        "smallest": 42.0,
        "first_caught": NOW.isoformat(),
    }


def test_summary_tie_breaks_by_fish_identity_deterministically():
    collection = empty_collection()
    collection = record_fish_catch(
        collection, fish_id="zeta", size=50, occurred_at=NOW
    ).collection
    collection = record_fish_catch(
        collection, fish_id="alpha", size=50, occurred_at=NOW
    ).collection

    summary = collection_summary(collection)
    assert summary.total_fish_caught == 2
    assert summary.unique_species_discovered == 2
    assert summary.largest_catch_id == "alpha"
    assert summary.largest_catch_size == 50
    assert summary.most_caught_id == "alpha"
    assert summary.most_caught_count == 1


def test_rarity_counts_depend_on_caller_owned_mapping_and_require_full_coverage():
    collection = record_fish_catch(
        empty_collection(), fish_id="trout", size=40, occurred_at=NOW
    ).collection
    collection = record_fish_catch(
        collection, fish_id="trout", size=45, occurred_at=NOW
    ).collection
    collection = record_fish_catch(
        collection, fish_id="leviathan", size=1000, occurred_at=NOW
    ).collection

    counts = rarity_catch_counts(
        collection, {"trout": "uncommon", "leviathan": "legendary"}
    )
    assert counts == {"legendary": 1, "uncommon": 2}

    with pytest.raises(ValueError, match="missing discovered fish"):
        rarity_catch_counts(collection, {"trout": "uncommon"})


def test_sizes_and_first_catch_time_fail_closed():
    with pytest.raises(ValueError, match="positive"):
        record_fish_catch(
            empty_collection(), fish_id="trout", size=0, occurred_at=NOW
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        record_fish_catch(
            empty_collection(),
            fish_id="trout",
            size=40,
            occurred_at=datetime(2026, 9, 15, 14, 0),
        )
