from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.frontier.encyclopedia import (
    CollectionState,
    FishCatchStats,
    FishSpeciesSpec,
    catalog_digest,
    collection_progress,
    collection_state_digest,
    discoverable_species,
    fishing_statistics,
    record_collection_catch,
    species_from_record,
    validate_collection_against_catalog,
)


def _catalog() -> tuple[FishSpeciesSpec, ...]:
    return (
        FishSpeciesSpec("minnow", "common", 1, 5, 15),
        FishSpeciesSpec("bass", "common", 3, 20, 60),
        FishSpeciesSpec("trout", "uncommon", 15, 25, 70),
        FishSpeciesSpec("koi", "rare", 20, 40, 90),
    )


def test_source_record_normalizes_portable_catalog_fields():
    spec = species_from_record(
        {
            "id": "bass",
            "name": "Largemouth Bass",
            "rarity": "common",
            "discovery_level": 3,
            "size_range": {"min": 20, "max": 60},
        }
    )
    assert spec == FishSpeciesSpec("bass", "common", 3, 20, 60)


def test_catalog_rejects_duplicate_ids_and_invalid_size_range():
    with pytest.raises(ValueError, match="max_size"):
        FishSpeciesSpec("bad", "common", 1, 20, 10)
    duplicate = (
        FishSpeciesSpec("bass", "common", 3, 20, 60),
        FishSpeciesSpec("bass", "rare", 20, 30, 90),
    )
    with pytest.raises(ValueError, match="duplicate fish species"):
        catalog_digest(duplicate)


def test_discovery_level_is_enforced_on_mutation_not_only_presentation():
    spec = FishSpeciesSpec("trout", "uncommon", 15, 25, 70)
    with pytest.raises(PermissionError, match="level 15"):
        record_collection_catch(
            CollectionState(),
            spec,
            player_level=14,
            size=40,
            occurred_at=datetime(2026, 9, 15, 10, tzinfo=timezone.utc),
        )


def test_negative_zero_and_out_of_catalog_sizes_fail_closed():
    spec = FishSpeciesSpec("bass", "common", 3, 20, 60)
    for size in (0, -1, 19, 61):
        with pytest.raises(ValueError):
            record_collection_catch(
                CollectionState(),
                spec,
                player_level=3,
                size=size,
                occurred_at=datetime(2026, 9, 15, 10, tzinfo=timezone.utc),
            )


def test_first_discovery_seeds_stats_and_repeated_catch_preserves_first_time():
    spec = FishSpeciesSpec("bass", "common", 3, 20, 60)
    first_time = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
    first = record_collection_catch(
        CollectionState(),
        spec,
        player_level=3,
        size=35,
        occurred_at=first_time,
    )
    assert first.is_new_discovery is True
    assert first.state.discovered_species == frozenset({"bass"})
    assert first.state.fish_stats["bass"] == FishCatchStats(
        caught=1,
        largest=35,
        smallest=35,
        first_caught=first_time,
    )

    second = record_collection_catch(
        first.state,
        spec,
        player_level=10,
        size=55,
        occurred_at=first_time + timedelta(hours=1),
    )
    third = record_collection_catch(
        second.state,
        spec,
        player_level=10,
        size=25,
        occurred_at=first_time + timedelta(hours=2),
    )
    stats = third.state.fish_stats["bass"]
    assert third.is_new_discovery is False
    assert stats.caught == 3
    assert stats.largest == 55
    assert stats.smallest == 25
    assert stats.first_caught == first_time


def test_collection_requires_exact_stats_coverage_for_discovered_species():
    now = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="exact coverage"):
        CollectionState(discovered_species=frozenset({"bass"}), fish_stats={})
    with pytest.raises(ValueError, match="exact coverage"):
        CollectionState(
            discovered_species=frozenset(),
            fish_stats={
                "bass": FishCatchStats(1, 30, 30, now),
            },
        )


def test_collection_catalog_validation_rejects_unknown_and_corrupt_sizes():
    now = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
    unknown = CollectionState(
        discovered_species=frozenset({"alien"}),
        fish_stats={"alien": FishCatchStats(1, 20, 20, now)},
    )
    with pytest.raises(ValueError, match="absent from catalog"):
        validate_collection_against_catalog(unknown, _catalog())

    corrupt = CollectionState(
        discovered_species=frozenset({"bass"}),
        fish_stats={"bass": FishCatchStats(1, 500, 500, now)},
    )
    with pytest.raises(ValueError, match="smallest size"):
        validate_collection_against_catalog(corrupt, _catalog())


def test_discoverable_query_is_level_sorted_and_can_exclude_owned():
    now = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
    state = CollectionState(
        discovered_species=frozenset({"minnow"}),
        fish_stats={"minnow": FishCatchStats(1, 10, 10, now)},
    )
    all_available = discoverable_species(
        _catalog(), player_level=15, state=state
    )
    assert [spec.id for spec in all_available] == ["minnow", "bass", "trout"]
    new_only = discoverable_species(
        _catalog(),
        player_level=15,
        state=state,
        include_discovered=False,
    )
    assert [spec.id for spec in new_only] == ["bass", "trout"]


def test_collection_progress_is_exact_by_rarity_and_completion():
    catalog = _catalog()
    now = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
    state = CollectionState(
        discovered_species=frozenset({"minnow", "trout"}),
        fish_stats={
            "minnow": FishCatchStats(1, 10, 10, now),
            "trout": FishCatchStats(1, 40, 40, now),
        },
    )
    progress = collection_progress(state, catalog)
    assert progress.total == 4
    assert progress.discovered == 2
    assert progress.completion_bps == 5_000
    assert progress.complete is False
    by_rarity = {row.rarity: row for row in progress.by_rarity}
    assert (by_rarity["common"].total, by_rarity["common"].discovered) == (2, 1)
    assert (by_rarity["uncommon"].total, by_rarity["uncommon"].discovered) == (1, 1)
    assert (by_rarity["rare"].total, by_rarity["rare"].discovered) == (1, 0)


def test_complete_collection_is_derived_not_mutated_separately():
    now = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
    state = CollectionState()
    for index, spec in enumerate(_catalog()):
        state = record_collection_catch(
            state,
            spec,
            player_level=100,
            size=spec.min_size,
            occurred_at=now + timedelta(minutes=index),
        ).state
    progress = collection_progress(state, _catalog())
    assert progress.complete is True
    assert progress.completion_bps == 10_000


def test_fishing_statistics_use_deterministic_tie_breaking():
    now = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
    state = CollectionState(
        discovered_species=frozenset({"bass", "minnow", "trout"}),
        fish_stats={
            "bass": FishCatchStats(4, 50, 25, now),
            "minnow": FishCatchStats(4, 15, 5, now),
            "trout": FishCatchStats(2, 50, 25, now),
        },
    )
    stats = fishing_statistics(state, _catalog())
    assert stats.total_fish_caught == 10
    assert stats.unique_species_discovered == 3
    # bass and trout tie at 50; canonical species id is the stable tiebreak.
    assert stats.largest_species_id == "bass"
    assert stats.largest_size == 50
    # bass and minnow tie at four catches; bass wins lexicographically.
    assert stats.most_caught_species_id == "bass"
    assert stats.most_caught_count == 4
    assert stats.catches_by_rarity == {"common": 8, "uncommon": 2}


def test_catalog_and_state_digests_are_order_independent_and_sensitive():
    catalog = _catalog()
    assert catalog_digest(catalog) == catalog_digest(tuple(reversed(catalog)))

    now = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
    left = CollectionState(
        discovered_species=frozenset({"bass", "minnow"}),
        fish_stats={
            "bass": FishCatchStats(2, 40, 30, now),
            "minnow": FishCatchStats(1, 10, 10, now),
        },
    )
    right = CollectionState(
        discovered_species=frozenset({"minnow", "bass"}),
        fish_stats={
            "minnow": FishCatchStats(1, 10, 10, now),
            "bass": FishCatchStats(2, 40, 30, now),
        },
    )
    assert collection_state_digest(left) == collection_state_digest(right)

    changed = CollectionState(
        discovered_species=left.discovered_species,
        fish_stats={
            "bass": FishCatchStats(3, 40, 30, now),
            "minnow": FishCatchStats(1, 10, 10, now),
        },
    )
    assert collection_state_digest(left) != collection_state_digest(changed)
