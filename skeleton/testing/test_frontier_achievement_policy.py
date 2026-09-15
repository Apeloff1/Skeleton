from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from skeleton.frontier.achievements import (
    AchievementState,
    achievement_from_record,
    achievement_summary,
    claim_achievement,
    claim_daily_reward,
    daily_reward_from_record,
    daily_reward_status,
    progress_percent,
    project_achievement,
    qualifies,
    unlock_qualified,
    update_stat,
)


def _achievement(
    achievement_id: str = "combo_5",
    *,
    requirement_type: str = "max_combo",
    count: int = 5,
    hidden: bool = False,
):
    return achievement_from_record(
        {
            "id": achievement_id,
            "name": "Combo Starter",
            "description": "Get a 5x combo",
            "category": "skill",
            "icon": "🔥",
            "xp_reward": 100,
            "coin_reward": 300,
            "gem_reward": 5,
            "title_reward": "Combo Initiate",
            "hidden": hidden,
            "requirement": {"type": requirement_type, "count": count},
        }
    )


def _daily_schedule():
    return tuple(
        daily_reward_from_record(record)
        for record in (
            {"day": 1, "rewards": {"coins": 100, "xp": 25}},
            {"day": 2, "rewards": {"coins": 150, "xp": 50}},
            {"day": 3, "rewards": {"coins": 200, "gems": 5, "xp": 75}},
            {"day": 4, "rewards": {"coins": 250, "xp": 100}},
            {"day": 5, "rewards": {"coins": 300, "xp": 125}},
            {"day": 6, "rewards": {"coins": 400, "gems": 10, "xp": 150}},
            {
                "day": 7,
                "rewards": {
                    "coins": 500,
                    "gems": 25,
                    "xp": 200,
                    "item": "weekly_mystery_box",
                },
            },
        )
    )


def test_source_record_normalizes_requirement_and_reward_plan():
    achievement = _achievement()
    assert achievement.id == "combo_5"
    assert achievement.category == "skill"
    assert achievement.requirement.kind == "max_combo"
    assert achievement.requirement.count == 5
    assert achievement.rewards == {
        "xp": 100,
        "coins": 300,
        "gems": 5,
        "title": "Combo Initiate",
    }


def test_max_combo_progress_uses_max_not_addition():
    state = AchievementState(stats={"max_combo": 3})
    state = update_stat(state, "max_combo", 2)
    assert state.stats["max_combo"] == 3
    state = update_stat(state, "max_combo", 8)
    assert state.stats["max_combo"] == 8


def test_regular_progress_is_additive_and_can_be_allowlisted():
    state = AchievementState(stats={"fish_caught": 4})
    state = update_stat(
        state,
        "fish_caught",
        3,
        allowed_stats=("fish_caught", "max_combo"),
    )
    assert state.stats["fish_caught"] == 7

    with pytest.raises(ValueError, match="unsupported achievement stat"):
        update_stat(state, "currency_spent", 1, allowed_stats=("fish_caught",))


def test_unlock_qualified_is_ordered_and_idempotent():
    combo = _achievement()
    level = _achievement(
        "level_10",
        requirement_type="level",
        count=10,
    )
    state = AchievementState(stats={"max_combo": 5})

    next_state, unlocked = unlock_qualified(
        (combo, level),
        state,
        signals={"level": 12},
    )
    assert [achievement.id for achievement in unlocked] == ["combo_5", "level_10"]
    assert next_state.unlocked == frozenset({"combo_5", "level_10"})

    repeated_state, repeated = unlock_qualified(
        (combo, level),
        next_state,
        signals={"level": 12},
    )
    assert repeated == ()
    assert repeated_state == next_state


def test_boolean_external_signals_preserve_source_guild_semantics():
    guild = _achievement(
        "join_guild",
        requirement_type="guild_joined",
        count=1,
    )
    state = AchievementState()
    assert not qualifies(guild, state, signals={"guild_joined": False})
    assert qualifies(guild, state, signals={"guild_joined": True})


def test_claim_is_one_shot_and_returns_mutation_free_reward_plan():
    achievement = _achievement()
    state = AchievementState(unlocked=frozenset({achievement.id}))
    claimed_state, plan = claim_achievement(achievement, state)

    assert claimed_state.claimed == frozenset({achievement.id})
    assert plan.increments == {"xp": 100, "coins": 300, "gems": 5}
    assert plan.titles == ("Combo Initiate",)
    assert plan.items == ()

    with pytest.raises(ValueError, match="already claimed"):
        claim_achievement(achievement, claimed_state)


def test_hidden_projection_masks_locked_secret_until_explicitly_disclosed():
    achievement = _achievement("storm_chaser", hidden=True)
    state = AchievementState(stats={"max_combo": 2})

    masked = project_achievement(achievement, state)
    assert masked["name"] == "???"
    assert masked["description"] == "Hidden achievement"
    assert "rewards" not in masked

    disclosed = project_achievement(achievement, state, include_hidden=True)
    assert disclosed["name"] == "Combo Starter"
    assert disclosed["target"] == 5
    assert disclosed["progress_percent"] == 40


def test_progress_is_capped_at_100_percent():
    achievement = _achievement()
    state = AchievementState(stats={"max_combo": 99})
    assert progress_percent(achievement, state) == 100


def test_summary_rejects_unknown_or_duplicate_state_catalog_ids():
    achievement = _achievement()
    assert achievement_summary(
        (achievement,),
        AchievementState(unlocked=frozenset({achievement.id})),
    ) == {
        "total": 1,
        "unlocked": 1,
        "claimed": 0,
        "completion_percent": 100.0,
    }

    with pytest.raises(KeyError, match="unknown achievements"):
        achievement_summary(
            (achievement,),
            AchievementState(unlocked=frozenset({"unknown"})),
        )

    with pytest.raises(ValueError, match="duplicate ids"):
        achievement_summary((achievement, achievement), AchievementState())


def test_state_rejects_claim_without_unlock():
    with pytest.raises(ValueError, match="must be unlocked first"):
        AchievementState(claimed=frozenset({"combo_5"}))


def test_daily_status_resets_stale_streak_and_selects_day_one():
    schedule = _daily_schedule()
    status = daily_reward_status(
        schedule,
        streak=6,
        last_claim=date(2026, 9, 10),
        today=date(2026, 9, 15),
    )
    assert status.current_streak == 0
    assert status.can_claim
    assert status.reward.day == 1


def test_daily_status_same_day_cannot_claim_and_keeps_current_reward():
    schedule = _daily_schedule()
    status = daily_reward_status(
        schedule,
        streak=7,
        last_claim="2026-09-15",
        today=date(2026, 9, 15),
    )
    assert not status.can_claim
    assert status.current_streak == 7
    assert status.reward.day == 7


def test_daily_claim_advances_consecutive_streak_and_cycles_schedule():
    schedule = _daily_schedule()
    claim = claim_daily_reward(
        schedule,
        streak=7,
        last_claim=date(2026, 9, 14),
        today=date(2026, 9, 15),
    )
    assert claim.streak == 8
    assert claim.reward.day == 1
    assert claim.increments == {"coins": 100, "xp": 25}


def test_daily_claim_day_seven_plans_item_without_inventory_mutation():
    schedule = _daily_schedule()
    claim = claim_daily_reward(
        schedule,
        streak=6,
        last_claim=datetime(2026, 9, 14, 21, 30, tzinfo=timezone.utc),
        today=date(2026, 9, 15),
    )
    assert claim.streak == 7
    assert claim.reward.day == 7
    assert claim.increments == {"coins": 500, "gems": 25, "xp": 200}
    assert claim.items == ("weekly_mystery_box",)


def test_daily_claim_rejects_repeat_future_dates_and_invalid_schedule():
    schedule = _daily_schedule()
    with pytest.raises(ValueError, match="already claimed today"):
        claim_daily_reward(
            schedule,
            streak=1,
            last_claim=date(2026, 9, 15),
            today=date(2026, 9, 15),
        )
    with pytest.raises(ValueError, match="cannot be in the future"):
        daily_reward_status(
            schedule,
            streak=1,
            last_claim=date(2026, 9, 16),
            today=date(2026, 9, 15),
        )
    with pytest.raises(ValueError, match="contiguous starting at 1"):
        daily_reward_status(
            (
                daily_reward_from_record({"day": 1, "rewards": {"coins": 1}}),
                daily_reward_from_record({"day": 3, "rewards": {"coins": 3}}),
            ),
            today=date(2026, 9, 15),
        )
