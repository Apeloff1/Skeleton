from __future__ import annotations

import pytest

from skeleton.frontier.lucky_wheel import (
    WheelConfig,
    WheelSlot,
    default_wheel_config,
    initial_wheel_budget,
    select_wheel_slot,
    spin_wheel,
)


def test_default_wheel_preserves_shared_source_mass_and_budgets():
    config = default_wheel_config()

    assert config.id == "daily_wheel"
    assert config.free_spins_per_day == 1
    assert config.ad_spins_per_day == 3
    assert config.gem_spin_cost == 50
    assert len(config.slots) == 9
    assert sum(slot.probability for slot in config.slots) == pytest.approx(1.0)
    assert config.slots[-1] == WheelSlot(8, "legendary_box", 1, 0.01, "legendary")


def test_probability_mass_and_slot_identity_fail_closed():
    with pytest.raises(ValueError, match="sum to 1"):
        WheelConfig(
            id="broken",
            slots=(WheelSlot(0, "coins", 1, 0.5, "common"),),
        )

    with pytest.raises(ValueError, match="duplicate"):
        WheelConfig(
            id="duplicate",
            slots=(
                WheelSlot(0, "coins", 1, 0.5, "common"),
                WheelSlot(0, "gems", 1, 0.5, "rare"),
            ),
        )


def test_injected_draw_selects_deterministically_without_global_rng():
    config = default_wheel_config()

    assert select_wheel_slot(config, 0.0).slot_id == 0
    assert select_wheel_slot(config, 0.249999).slot_id == 0
    assert select_wheel_slot(config, 0.250001).slot_id == 1
    assert select_wheel_slot(config, 0.999999).slot_id == 8

    with pytest.raises(ValueError, match=r"\[0, 1\)"):
        select_wheel_slot(config, 1.0)


def test_unknown_spin_type_cannot_bypass_quota_or_cost_checks():
    config = default_wheel_config()
    budget = initial_wheel_budget(config)

    with pytest.raises(ValueError, match="unsupported"):
        spin_wheel(config, budget, spin_type="unmetered", draw=0.1)


def test_free_spin_consumes_only_free_budget_and_returns_reward_plan():
    config = default_wheel_config()
    budget = initial_wheel_budget(config)

    plan = spin_wheel(config, budget, spin_type="free", draw=0.1)

    assert plan.slot.slot_id == 0
    assert plan.budget.free_spins_remaining == 0
    assert plan.budget.ad_spins_remaining == 3
    assert plan.budget.total_spins == 1
    assert plan.gem_debit == 0
    assert plan.reward.currency_increments == {"coins": 50}

    with pytest.raises(PermissionError, match="no free"):
        spin_wheel(config, plan.budget, spin_type="free", draw=0.1)


def test_ad_spin_requires_verified_completion_before_budget_is_consumed():
    config = default_wheel_config()
    budget = initial_wheel_budget(config)

    with pytest.raises(PermissionError, match="verified ad"):
        spin_wheel(config, budget, spin_type="ad", draw=0.7)

    plan = spin_wheel(
        config,
        budget,
        spin_type="ad",
        draw=0.7,
        ad_verified=True,
    )
    assert plan.budget.ad_spins_remaining == 2
    assert plan.budget.free_spins_remaining == 1
    assert plan.reward.energy_increment == 20


def test_gem_spin_preflights_balance_and_returns_debit_not_wallet_mutation():
    config = default_wheel_config()
    budget = initial_wheel_budget(config)

    with pytest.raises(PermissionError, match="insufficient gems"):
        spin_wheel(config, budget, spin_type="gem", draw=0.9, gem_balance=49)

    plan = spin_wheel(config, budget, spin_type="gem", draw=0.9, gem_balance=50)
    assert plan.gem_debit == 50
    assert plan.budget.free_spins_remaining == 1
    assert plan.budget.ad_spins_remaining == 3
    assert plan.budget.total_spins == 1


def test_reward_projection_separates_energy_inventory_and_currency():
    config = default_wheel_config()
    budget = initial_wheel_budget(config)

    energy = spin_wheel(config, budget, spin_type="free", draw=0.7)
    assert energy.reward.energy_increment == 20
    assert energy.reward.currency_increments == {}

    bait = spin_wheel(
        config,
        budget,
        spin_type="ad",
        draw=0.8,
        ad_verified=True,
    )
    assert bait.reward.inventory_increments == {"bait": 5}

    gems = spin_wheel(config, budget, spin_type="gem", draw=0.9, gem_balance=50)
    assert gems.reward.currency_increments == {"gems": 10}
