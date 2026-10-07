from __future__ import annotations

import pytest

from skeleton.frontier.season_pass import (
    SeasonPassSpec,
    SeasonProgress,
    SeasonReward,
    SeasonTier,
    activate_premium,
    add_season_xp,
    claim_season_reward,
    default_season_pass,
    generate_default_season_tiers,
    initial_season_progress,
    xp_to_next_level,
)


def test_default_tier_generation_preserves_shared_source_formulas():
    tiers = generate_default_season_tiers()

    assert len(tiers) == 50
    assert tiers[0].required_xp == 100
    assert tiers[1].required_xp == 250
    assert tiers[2].required_xp == 400
    assert tiers[2].free_reward == SeasonReward("bait", amount=5)
    assert tiers[4].free_reward == SeasonReward("mystery_box")
    assert tiers[4].premium_reward == SeasonReward("gems", amount=55)
    assert tiers[9].premium_reward == SeasonReward(
        "exclusive_cosmetic",
        item_id="season_cosmetic_10",
    )
    assert tiers[49].premium_reward == SeasonReward(
        "legendary_rod",
        item_id="season_rod",
        exclusive=True,
    )


def test_tier_catalog_rejects_gaps_and_reordering():
    with pytest.raises(ValueError, match="contiguous"):
        SeasonPassSpec(
            id="season-1",
            tiers=(
                SeasonTier(1, 100, SeasonReward("coins", 50), None),
                SeasonTier(3, 400, SeasonReward("bait", 5), None),
            ),
        )


def test_xp_rollover_drains_every_crossed_threshold():
    spec = default_season_pass("season-1")
    progress = initial_season_progress(spec)

    plan = add_season_xp(spec, progress, 800)

    # Level 1 costs 100, level 2 costs 250, level 3 costs 400.
    assert plan.levels_gained == 3
    assert plan.progress.current_level == 4
    assert plan.progress.current_xp == 50
    assert plan.applied_xp == 800
    assert xp_to_next_level(spec, plan.progress) == 500


def test_progress_rejects_unconsumed_threshold_xp():
    spec = default_season_pass("season-1")
    malformed = SeasonProgress("season-1", current_level=2, current_xp=250)

    with pytest.raises(ValueError, match="normalized"):
        xp_to_next_level(spec, malformed)


def test_free_reward_claim_is_idempotent_and_wallet_neutral():
    spec = default_season_pass("season-1")
    progress = initial_season_progress(spec)

    plan = claim_season_reward(spec, progress, level=1)

    assert plan.currency_increments == {"coins": 50}
    assert plan.inventory_increments == {}
    assert plan.unlock_items == ()
    assert 1 in plan.progress.claimed_free_rewards

    with pytest.raises(ValueError, match="already claimed"):
        claim_season_reward(spec, plan.progress, level=1)


def test_unreached_reward_cannot_be_claimed():
    spec = default_season_pass("season-1")
    progress = initial_season_progress(spec)

    with pytest.raises(PermissionError, match="not been reached"):
        claim_season_reward(spec, progress, level=2)


def test_premium_activation_requires_external_verified_entitlement():
    spec = default_season_pass("season-1")
    progress = initial_season_progress(spec)

    with pytest.raises(PermissionError, match="verified entitlement"):
        activate_premium(spec, progress, entitlement_verified=False)

    premium = activate_premium(spec, progress, entitlement_verified=True)
    assert premium.is_premium


def test_premium_claim_requires_entitlement_and_returns_item_plan():
    spec = default_season_pass("season-1")
    progress = initial_season_progress(spec)
    progress = add_season_xp(spec, progress, sum(t.required_xp for t in spec.tiers[:49])).progress
    assert progress.current_level == 50

    with pytest.raises(PermissionError, match="premium"):
        claim_season_reward(spec, progress, level=50, premium=True)

    premium = activate_premium(spec, progress, entitlement_verified=True)
    plan = claim_season_reward(spec, premium, level=50, premium=True)

    assert plan.currency_increments == {}
    assert plan.inventory_increments == {}
    assert plan.unlock_items == ("season_rod",)
    assert 50 in plan.progress.claimed_premium_rewards


def test_catalog_and_progress_identity_must_match():
    spec = default_season_pass("season-1")
    other_progress = SeasonProgress("season-2")

    with pytest.raises(ValueError, match="does not belong"):
        add_season_xp(spec, other_progress, 100)


def test_max_level_ignores_further_xp_instead_of_accumulating_unbounded_state():
    spec = SeasonPassSpec(
        id="short-season",
        tiers=(SeasonTier(1, 100, SeasonReward("coins", 50), SeasonReward("coins", 100)),),
    )
    progress = initial_season_progress(spec)

    plan = add_season_xp(spec, progress, 10_000)

    assert plan.progress == progress
    assert plan.applied_xp == 0
    assert plan.levels_gained == 0
