from __future__ import annotations

import pytest

from skeleton.frontier.achievements import AchievementState, qualifies, unlock_qualified
from skeleton.frontier.biotope import BiotopeProgress
from skeleton.frontier.biotope_achievement_adapters import (
    biotope_achievement_from_record,
    biotope_progress_achievement_signals,
    record_biotope_achievement_catch,
    requirement_signals_for_achievement,
)


def test_nested_source_rewards_and_size_threshold_normalize_to_canonical_spec():
    spec = biotope_achievement_from_record(
        {
            "id": "trophy_hunter_lake",
            "name": "Trophy Hunter",
            "description": "Catch a fish over 100cm in a lake",
            "biotope": "freshwater_lake",
            "category": "size",
            "icon": "trophy",
            "requirement": {"type": "lake_trophy", "size": 100},
            "rewards": {"xp": 400, "coins": 2000, "gems": 20},
        }
    )

    assert spec.id == "trophy_hunter_lake"
    assert spec.requirement.kind == "lake_trophy"
    assert spec.requirement.count == 100
    assert spec.rewards == {"xp": 400, "coins": 2000, "gems": 20}
    assert spec.metadata["biotope"] == "freshwater_lake"
    assert spec.metadata["source_threshold_kind"] == "size"


def test_converter_rejects_ambiguous_thresholds_and_unknown_reward_shapes():
    base = {
        "id": "bad",
        "name": "Bad",
        "biotope": "river",
        "category": "biotope",
        "requirement": {"type": "river_catches", "count": 10, "size": 20},
        "rewards": {},
    }
    with pytest.raises(ValueError, match="exactly one"):
        biotope_achievement_from_record(base)

    invalid_reward = dict(base)
    invalid_reward["requirement"] = {"type": "river_catches", "count": 10}
    invalid_reward["rewards"] = {"shell_command": "rm -rf /"}
    with pytest.raises(ValueError, match="unsupported"):
        biotope_achievement_from_record(invalid_reward)


def test_freshwater_lake_catch_updates_source_lake_alias_and_trophy_max():
    state = record_biotope_achievement_catch(
        AchievementState(),
        biotope_id="freshwater_lake",
        stage_id="deep_lake",
        rarity="rare",
        size_cm=120,
        species_groups=("bass",),
    )
    state = record_biotope_achievement_catch(
        state,
        biotope_id="freshwater_lake",
        stage_id="deep_lake",
        rarity="common",
        size_cm=80,
        species_groups=("bass",),
    )

    assert state.stats["lake_catches"] == 2
    assert "freshwater_lake_catches" not in state.stats
    assert state.stats["deep_lake_catches"] == 2
    assert state.stats["rare_catches"] == 1
    assert state.stats["common_catches"] == 1
    assert state.stats["bass_catches"] == 2
    assert state.stats["lake_trophy"] == 120


def test_species_groups_are_explicit_and_never_inferred_from_fish_identity():
    state = record_biotope_achievement_catch(
        AchievementState(),
        biotope_id="river",
        stage_id="lowland_river",
        rarity="common",
        size_cm=40,
        species_groups=(),
    )
    assert "trout_catches" not in state.stats

    with pytest.raises(TypeError, match="iterable"):
        record_biotope_achievement_catch(
            state,
            biotope_id="river",
            stage_id="lowland_river",
            rarity="common",
            size_cm=40,
            species_groups="trout",
        )


def test_legendary_stage_signal_is_derived_without_fish_catalog_dependency():
    state = record_biotope_achievement_catch(
        AchievementState(),
        biotope_id="brackish",
        stage_id="delta",
        rarity="legendary",
        size_cm=90,
    )

    assert state.stats["brackish_catches"] == 1
    assert state.stats["legendary_catches"] == 1
    assert state.stats["delta_legendary"] == 1


def _world_progress(each: int) -> BiotopeProgress:
    return BiotopeProgress(
        unlocked_biotopes=frozenset(
            {"freshwater_lake", "saltwater", "brackish", "river"}
        ),
        unlocked_stages=frozenset({"pond"}),
        current_biotope="freshwater_lake",
        current_stage="pond",
        biotope_xp={
            "freshwater_lake": 0,
            "saltwater": 0,
            "brackish": 0,
            "river": 0,
        },
        biotope_level={
            "freshwater_lake": 1,
            "saltwater": 1,
            "brackish": 1,
            "river": 1,
        },
        fish_caught_by_biotope={
            "freshwater_lake": each,
            "saltwater": each,
            "brackish": each,
            "river": each,
        },
    )


def test_cross_biotope_signals_normalize_lake_and_count_fished_mastered():
    signals = biotope_progress_achievement_signals(
        _world_progress(100), mastered_catch_threshold=100
    )

    assert signals["lake_catches"] == 100
    assert signals["saltwater_catches"] == 100
    assert signals["brackish_catches"] == 100
    assert signals["river_catches"] == 100
    assert signals["biotopes_fished"] == 4
    assert signals["biotopes_mastered"] == 4


def test_world_angler_each_semantics_compose_with_canonical_qualification():
    world_angler = biotope_achievement_from_record(
        {
            "id": "world_angler",
            "name": "World Angler",
            "biotope": "all",
            "category": "exploration",
            "requirement": {"type": "biotopes_mastered", "count": 4, "each": 100},
            "rewards": {"xp": 5000, "coins": 25000, "gems": 250, "title": "World Angler"},
        }
    )

    below = requirement_signals_for_achievement(world_angler, _world_progress(99))
    complete = requirement_signals_for_achievement(world_angler, _world_progress(100))
    assert not qualifies(world_angler, AchievementState(), signals=below)
    assert qualifies(world_angler, AchievementState(), signals=complete)

    unlocked, newly = unlock_qualified(
        (world_angler,), AchievementState(), signals=complete
    )
    assert world_angler.id in unlocked.unlocked
    assert newly == (world_angler,)
