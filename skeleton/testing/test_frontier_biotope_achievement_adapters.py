from __future__ import annotations

import pytest

from skeleton.frontier.achievements import AchievementState, claim_achievement
from skeleton.frontier.biotope_achievement_adapters import (
    biotope_achievement_from_record,
    biotope_requirement_value,
    empty_biotope_catch_evidence,
    record_biotope_catch,
    synchronize_biotope_achievement_state,
)


def _achievement(
    achievement_id: str,
    requirement: dict,
    *,
    biotope: str = "all",
    rewards: dict | None = None,
):
    return biotope_achievement_from_record(
        {
            "id": achievement_id,
            "name": achievement_id.replace("_", " ").title(),
            "description": "test",
            "biotope": biotope,
            "category": "collection",
            "icon": "test",
            "requirement": requirement,
            "rewards": rewards or {"xp": 10, "coins": 20},
        }
    )


def test_source_shape_normalizes_nested_rewards_and_size_threshold():
    trophy = _achievement(
        "trophy_hunter_lake",
        {"type": "lake_trophy", "size": 100},
        biotope="freshwater_lake",
        rewards={"xp": 400, "coins": 2_000, "gems": 20, "title": "Trophy Hunter"},
    )

    assert trophy.requirement.kind == "lake_trophy"
    assert trophy.requirement.count == 100
    assert trophy.rewards == {
        "xp": 400,
        "coins": 2_000,
        "gems": 20,
        "title": "Trophy Hunter",
    }
    assert trophy.metadata["requirement_threshold_kind"] == "size"


def test_source_shape_rejects_ambiguous_requirement_thresholds():
    with pytest.raises(ValueError, match="exactly one"):
        _achievement(
            "ambiguous",
            {"type": "fish", "count": 1, "size": 10},
        )


def test_catch_evidence_repairs_source_family_tracking_gap():
    evidence = record_biotope_catch(
        empty_biotope_catch_evidence(),
        fish_id="largemouth_bass",
        biotope_id="freshwater_lake",
        stage_id="shallow_lake",
        size=55,
        rarity="common",
    )

    # The source uses fish_id.split("_")[0], which loses the bass family here.
    assert evidence.counts["bass_catches"] == 1
    assert evidence.counts["freshwater_lake_catches"] == 1
    assert evidence.counts["shallow_lake_catches"] == 1


def test_source_requirement_count_aliases_repair_lake_and_arctic_mismatches():
    lake = _achievement(
        "lake_beginner",
        {"type": "lake_catches", "count": 1},
        biotope="freshwater_lake",
    )
    arctic = _achievement(
        "arctic_fisher",
        {"type": "arctic_catches", "count": 1},
        biotope="saltwater",
    )
    evidence = record_biotope_catch(
        empty_biotope_catch_evidence(),
        fish_id="bluegill",
        biotope_id="freshwater_lake",
        stage_id="pond",
        size=20,
        rarity="common",
    )
    evidence = record_biotope_catch(
        evidence,
        fish_id="arctic_cod",
        biotope_id="saltwater",
        stage_id="arctic_ocean",
        size=80,
        rarity="common",
    )

    assert biotope_requirement_value(lake, evidence) == 1
    assert biotope_requirement_value(arctic, evidence) == 1


def test_distinct_stage_species_requirement_is_derived_not_manually_mutated():
    achievement = _achievement(
        "reef_diver",
        {"type": "reef_species", "count": 2},
        biotope="saltwater",
    )
    evidence = empty_biotope_catch_evidence()
    for fish_id in ("parrotfish", "grouper", "grouper"):
        evidence = record_biotope_catch(
            evidence,
            fish_id=fish_id,
            biotope_id="saltwater",
            stage_id="coral_reef",
            size=40,
            rarity="common",
        )

    assert biotope_requirement_value(achievement, evidence) == 2
    state, unlocked = synchronize_biotope_achievement_state(
        [achievement], AchievementState(), evidence
    )
    assert [item.id for item in unlocked] == ["reef_diver"]
    assert "reef_diver" in state.unlocked


def test_world_angler_enforces_each_per_biotope_not_aggregate_count():
    achievement = _achievement(
        "world_angler",
        {"type": "biotopes_mastered", "count": 4, "each": 2},
    )
    evidence = empty_biotope_catch_evidence()
    for biotope in ("saltwater", "freshwater_lake", "brackish", "river"):
        evidence = record_biotope_catch(
            evidence,
            fish_id=f"{biotope}_fish_a",
            biotope_id=biotope,
            stage_id=f"{biotope}_stage",
            size=10,
            rarity="common",
        )

    assert biotope_requirement_value(achievement, evidence) == 0
    state, unlocked = synchronize_biotope_achievement_state(
        [achievement], AchievementState(), evidence
    )
    assert unlocked == ()
    assert "world_angler" not in state.unlocked

    for biotope in ("saltwater", "freshwater_lake", "brackish", "river"):
        evidence = record_biotope_catch(
            evidence,
            fish_id=f"{biotope}_fish_b",
            biotope_id=biotope,
            stage_id=f"{biotope}_stage",
            size=11,
            rarity="common",
        )

    state, unlocked = synchronize_biotope_achievement_state(
        [achievement], state, evidence
    )
    assert biotope_requirement_value(achievement, evidence) == 4
    assert [item.id for item in unlocked] == ["world_angler"]
    assert "world_angler" in state.unlocked


def test_trophy_and_legendary_cross_biotope_evidence_are_explicit():
    trophy = _achievement(
        "size_matters",
        {"type": "trophy_biotopes", "count": 2},
    )
    legendary = _achievement(
        "legendary_collector",
        {"type": "legendary_per_biotope", "count": 2},
    )
    evidence = empty_biotope_catch_evidence()
    evidence = record_biotope_catch(
        evidence,
        fish_id="lake_legend",
        biotope_id="freshwater_lake",
        stage_id="ancient_lake",
        size=150,
        rarity="legendary",
        is_trophy=True,
    )
    evidence = record_biotope_catch(
        evidence,
        fish_id="ocean_legend",
        biotope_id="saltwater",
        stage_id="deep_sea",
        size=250,
        rarity="legendary",
        is_trophy=True,
    )

    assert biotope_requirement_value(trophy, evidence) == 2
    assert biotope_requirement_value(legendary, evidence) == 2


def test_size_requirement_uses_max_size_for_declared_biotope():
    achievement = _achievement(
        "trophy_hunter_lake",
        {"type": "lake_trophy", "size": 100},
        biotope="freshwater_lake",
    )
    evidence = empty_biotope_catch_evidence()
    evidence = record_biotope_catch(
        evidence,
        fish_id="lake_trout",
        biotope_id="freshwater_lake",
        stage_id="deep_lake",
        size=99,
        rarity="rare",
    )
    assert biotope_requirement_value(achievement, evidence) == 99

    evidence = record_biotope_catch(
        evidence,
        fish_id="lake_sturgeon",
        biotope_id="freshwater_lake",
        stage_id="deep_lake",
        size=120,
        rarity="rare",
    )
    state, unlocked = synchronize_biotope_achievement_state(
        [achievement], AchievementState(), evidence
    )
    assert [item.id for item in unlocked] == ["trophy_hunter_lake"]
    assert state.stats["lake_trophy"] == 120


def test_delta_legendary_is_derived_from_stage_and_rarity():
    achievement = _achievement(
        "delta_monster",
        {"type": "delta_legendary", "count": 1},
        biotope="brackish",
    )
    evidence = record_biotope_catch(
        empty_biotope_catch_evidence(),
        fish_id="delta_leviathan",
        biotope_id="brackish",
        stage_id="delta",
        size=300,
        rarity="legendary",
    )
    assert biotope_requirement_value(achievement, evidence) == 1


def test_synchronization_delegates_claim_semantics_to_canonical_kernel():
    achievement = _achievement(
        "lake_beginner",
        {"type": "lake_catches", "count": 1},
        biotope="freshwater_lake",
        rewards={"xp": 100, "coins": 500},
    )
    evidence = record_biotope_catch(
        empty_biotope_catch_evidence(),
        fish_id="bluegill",
        biotope_id="freshwater_lake",
        stage_id="pond",
        size=20,
        rarity="common",
    )
    state, unlocked = synchronize_biotope_achievement_state(
        [achievement], AchievementState(), evidence
    )
    assert [item.id for item in unlocked] == ["lake_beginner"]

    claimed, reward = claim_achievement(achievement, state)
    assert "lake_beginner" in claimed.claimed
    assert reward.increments == {"xp": 100, "coins": 500}
