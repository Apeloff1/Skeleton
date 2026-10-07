from __future__ import annotations

from datetime import date

import pytest

from skeleton.frontier.vip_daily import (
    CatchOfDay,
    CatchOfDayState,
    VIPPointState,
    award_vip_points,
    claim_catch_reward,
    claim_vip_milestone,
    generate_catch_of_day,
    record_catch,
    source_default_milestones,
)


def test_catch_generation_is_stable_and_level_gated():
    day = date(2026, 9, 15)
    first = generate_catch_of_day("user-1", day, player_level=10)
    second = generate_catch_of_day("user-1", day, player_level=10)
    assert first == second
    assert first.challenge.difficulty == "easy"

    high = generate_catch_of_day("user-1", day, player_level=60)
    assert high.challenge.difficulty in {"easy", "medium", "hard", "legendary"}


def test_record_catch_uses_exact_fish_identity_not_substrings():
    challenge = CatchOfDay(
        subject_id="user-1",
        challenge_date=date(2026, 9, 15),
        difficulty="easy",
        target_fish_id="bass",
        target_count=2,
        vip_points=25,
        bonus_multiplier_bps=10_000,
    )
    state = CatchOfDayState(challenge=challenge)

    # Source fuzzy matching could accept names containing the target token.
    state = record_catch(
        state,
        subject_id="user-1",
        fish_id="largemouth_bass",
        catch_date=date(2026, 9, 15),
    )
    assert state.progress == 0

    state = record_catch(
        state,
        subject_id="user-1",
        fish_id="bass",
        catch_date=date(2026, 9, 15),
    )
    assert state.progress == 1


def test_catch_progress_caps_at_target_and_becomes_completed():
    challenge = CatchOfDay(
        subject_id="u",
        challenge_date=date(2026, 9, 15),
        difficulty="easy",
        target_fish_id="trout",
        target_count=1,
        vip_points=25,
        bonus_multiplier_bps=10_000,
    )
    state = record_catch(
        CatchOfDayState(challenge=challenge),
        subject_id="u",
        fish_id="trout",
        catch_date=date(2026, 9, 15),
    )
    assert state.progress == 1
    assert state.completed is True
    assert record_catch(
        state,
        subject_id="u",
        fish_id="trout",
        catch_date=date(2026, 9, 15),
    ) == state


def test_catch_reward_is_single_use_and_preserves_source_multiplier():
    challenge = CatchOfDay(
        subject_id="u",
        challenge_date=date(2026, 9, 15),
        difficulty="medium",
        target_fish_id="salmon",
        target_count=1,
        vip_points=50,
        bonus_multiplier_bps=12_500,
    )
    completed = CatchOfDayState(
        challenge=challenge,
        progress=1,
        completed=True,
    )
    plan = claim_catch_reward(
        completed,
        subject_id="u",
        claim_date=date(2026, 9, 15),
        vip_tier=2,
    )
    # int(50 * 1.2 * 1.25) = 75; int(500 * 1.25) = 625.
    assert plan.vip_points == 75
    assert plan.bonus_coins == 625
    assert plan.state.claimed is True

    with pytest.raises(ValueError, match="already claimed"):
        claim_catch_reward(
            plan.state,
            subject_id="u",
            claim_date=date(2026, 9, 15),
            vip_tier=2,
        )


def test_catch_claim_rejects_wrong_subject_date_and_incomplete_state():
    challenge = CatchOfDay(
        subject_id="u",
        challenge_date=date(2026, 9, 15),
        difficulty="easy",
        target_fish_id="perch",
        target_count=2,
        vip_points=25,
        bonus_multiplier_bps=10_000,
    )
    incomplete = CatchOfDayState(challenge=challenge)
    with pytest.raises(ValueError, match="not completed"):
        claim_catch_reward(
            incomplete,
            subject_id="u",
            claim_date=date(2026, 9, 15),
            vip_tier=1,
        )

    completed = CatchOfDayState(challenge=challenge, progress=2, completed=True)
    with pytest.raises(PermissionError, match="another subject"):
        claim_catch_reward(
            completed,
            subject_id="other",
            claim_date=date(2026, 9, 15),
            vip_tier=1,
        )
    with pytest.raises(ValueError, match="expired"):
        claim_catch_reward(
            completed,
            subject_id="u",
            claim_date=date(2026, 9, 16),
            vip_tier=1,
        )


def test_vip_points_accumulate_and_milestones_do_not_spend_points():
    state = award_vip_points(VIPPointState(), 250)
    assert state.available_points == 250
    assert state.lifetime_points == 250

    reward = source_default_milestones()[1]
    plan = claim_vip_milestone(state, reward)
    assert plan.state.available_points == 250
    assert plan.state.lifetime_points == 250
    assert 250 in plan.state.claimed_milestones
    assert plan.reward.energy_refills == 1


def test_vip_milestone_is_claimable_once_and_requires_threshold():
    reward = source_default_milestones()[0]
    with pytest.raises(PermissionError, match="not enough"):
        claim_vip_milestone(
            VIPPointState(available_points=99, lifetime_points=99), reward
        )

    state = VIPPointState(available_points=100, lifetime_points=100)
    first = claim_vip_milestone(state, reward)
    with pytest.raises(ValueError, match="already claimed"):
        claim_vip_milestone(first.state, reward)


def test_default_milestones_preserve_source_reward_shape():
    milestones = source_default_milestones()
    assert [reward.milestone for reward in milestones] == [100, 250, 500, 1000, 2500, 5000]
    assert milestones[3].vip_days == 3
    assert milestones[4].item_grants == ("vip_master_rod",)
    assert milestones[5].title_grants == ("VIP Legend",)
