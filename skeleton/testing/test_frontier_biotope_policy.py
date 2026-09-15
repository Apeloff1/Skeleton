from __future__ import annotations

import pytest

from skeleton.frontier.biotope import (
    BiotopeProgress,
    BiotopeSpec,
    BiotopeStageSpec,
    calculate_biotope_bonus,
    can_unlock_biotope,
    enter_stage,
    initial_progress,
    record_catch,
    unlock_biotope,
    unlock_stage,
    unlockable_biotopes,
    unlockable_stages,
)


def _lake_stages() -> tuple[BiotopeStageSpec, ...]:
    return (
        BiotopeStageSpec(
            id="pond",
            biotope_id="freshwater_lake",
            stage_number=1,
            unlock_level=1,
        ),
        BiotopeStageSpec(
            id="shallow_lake",
            biotope_id="freshwater_lake",
            stage_number=2,
            unlock_level=10,
        ),
        BiotopeStageSpec(
            id="deep_lake",
            biotope_id="freshwater_lake",
            stage_number=3,
            unlock_level=25,
        ),
    )


def _salt_stages() -> tuple[BiotopeStageSpec, ...]:
    return (
        BiotopeStageSpec(
            id="coastal_shallows",
            biotope_id="saltwater",
            stage_number=1,
            unlock_level=15,
        ),
        BiotopeStageSpec(
            id="coral_reef",
            biotope_id="saltwater",
            stage_number=2,
            unlock_level=25,
        ),
    )


def test_initial_progress_matches_source_default_progression_seed():
    progress = initial_progress()

    assert progress.unlocked_biotopes == frozenset({"freshwater_lake"})
    assert progress.unlocked_stages == frozenset({"pond"})
    assert progress.current_biotope == "freshwater_lake"
    assert progress.current_stage == "pond"
    assert progress.biotope_xp == {"freshwater_lake": 0}
    assert progress.biotope_level == {"freshwater_lake": 1}
    assert progress.fish_caught_by_biotope == {"freshwater_lake": 0}


def test_mastery_bonus_preserves_source_formula():
    bonus = calculate_biotope_bonus(7)

    assert bonus.catch_rate == pytest.approx(1.14)
    assert bonus.rare_chance == pytest.approx(1.21)
    assert bonus.xp_bonus == pytest.approx(1.07)
    assert bonus.coin_bonus == pytest.approx(1.105)


def test_biotope_unlock_is_level_gated_and_seeds_first_stage():
    progress = initial_progress()
    saltwater = BiotopeSpec(id="saltwater", unlock_level=15, required_boat=True)

    assert not can_unlock_biotope(
        progress,
        saltwater,
        player_level=14,
        has_boat=True,
    )
    assert not can_unlock_biotope(
        progress,
        saltwater,
        player_level=15,
        has_boat=False,
    )
    assert can_unlock_biotope(
        progress,
        saltwater,
        player_level=15,
        has_boat=True,
    )

    unlocked = unlock_biotope(
        progress,
        saltwater,
        stages=_salt_stages(),
        player_level=15,
        has_boat=True,
    )

    assert unlocked.unlocked_biotopes == frozenset({"freshwater_lake", "saltwater"})
    assert "coastal_shallows" in unlocked.unlocked_stages
    assert unlocked.biotope_level["saltwater"] == 1
    assert unlocked.biotope_xp["saltwater"] == 0
    assert unlocked.fish_caught_by_biotope["saltwater"] == 0


def test_stage_unlock_requires_level_and_previous_stage():
    progress = initial_progress()
    stages = _lake_stages()

    with pytest.raises(PermissionError, match="player level 10"):
        unlock_stage(progress, stages[1], stages=stages, player_level=9)

    shallow = unlock_stage(progress, stages[1], stages=stages, player_level=10)
    assert "shallow_lake" in shallow.unlocked_stages

    with pytest.raises(PermissionError, match="previous stage"):
        unlock_stage(progress, stages[2], stages=stages, player_level=25)

    deep = unlock_stage(shallow, stages[2], stages=stages, player_level=25)
    assert "deep_lake" in deep.unlocked_stages


def test_enter_stage_requires_unlock_and_updates_location_atomically():
    stages = _lake_stages()
    progress = initial_progress()

    with pytest.raises(PermissionError, match="not unlocked"):
        enter_stage(progress, stages[1])

    progress = unlock_stage(progress, stages[1], stages=stages, player_level=10)
    entered = enter_stage(progress, stages[1])

    assert entered.current_biotope == "freshwater_lake"
    assert entered.current_stage == "shallow_lake"


def test_record_catch_drains_all_crossed_mastery_thresholds():
    plan = record_catch(
        initial_progress(),
        "freshwater_lake",
        xp_earned=650,
    )

    # level 1 costs 100, level 2 costs 200, level 3 costs 300.
    assert plan.levels_gained == 3
    assert plan.progress.biotope_level["freshwater_lake"] == 4
    assert plan.progress.biotope_xp["freshwater_lake"] == 50
    assert plan.progress.fish_caught_by_biotope["freshwater_lake"] == 1
    assert plan.bonus == calculate_biotope_bonus(4)


def test_record_catch_rejects_locked_biotope_and_negative_xp():
    progress = initial_progress()

    with pytest.raises(PermissionError, match="locked biotope"):
        record_catch(progress, "saltwater", xp_earned=10)

    with pytest.raises(ValueError, match="must not be negative"):
        record_catch(progress, "freshwater_lake", xp_earned=-1)


def test_unlockable_queries_are_deterministic_and_fail_closed():
    progress = initial_progress()
    biotopes = (
        BiotopeSpec(id="river", unlock_level=8),
        BiotopeSpec(id="saltwater", unlock_level=15, required_boat=True),
        BiotopeSpec(id="brackish", unlock_level=25),
    )

    assert [spec.id for spec in unlockable_biotopes(
        progress,
        biotopes,
        player_level=20,
        has_boat=False,
    )] == ["river"]

    stages = _lake_stages()
    assert [stage.id for stage in unlockable_stages(
        progress,
        stages,
        player_level=25,
    )] == ["shallow_lake"]


def test_duplicate_or_gapped_stage_topology_is_rejected():
    progress = initial_progress()
    duplicate = (
        BiotopeStageSpec("pond", "freshwater_lake", 1, 1),
        BiotopeStageSpec("pond_alt", "freshwater_lake", 1, 1),
    )
    with pytest.raises(ValueError, match="duplicate stage number"):
        unlockable_stages(progress, duplicate, player_level=10)

    gapped = (
        BiotopeStageSpec("pond", "freshwater_lake", 1, 1),
        BiotopeStageSpec("deep_lake", "freshwater_lake", 3, 25),
    )
    with pytest.raises(ValueError, match="contiguous"):
        unlock_stage(progress, gapped[1], stages=gapped, player_level=25)


def test_progress_rejects_tracking_locked_biotope():
    with pytest.raises(ValueError, match="only track unlocked"):
        BiotopeProgress(
            unlocked_biotopes=frozenset({"freshwater_lake"}),
            unlocked_stages=frozenset({"pond"}),
            current_biotope="freshwater_lake",
            current_stage="pond",
            biotope_xp={"saltwater": 0},
            biotope_level={"freshwater_lake": 1},
            fish_caught_by_biotope={"freshwater_lake": 0},
        )
