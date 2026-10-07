from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.frontier.energy import (
    DEFAULT_ENERGY_POLICY,
    EnergyBoosterSpec,
    EnergyState,
    apply_booster,
    consume_energy,
    energy_booster_from_record,
    energy_status,
    initialize_energy,
    max_energy_for_level,
    perfect_catch_refund,
    regenerate_energy,
    restore_energy,
    restore_from_ad,
    sync_max_energy,
)


T0 = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


def _state(current=50, *, maximum=100, **kwargs):
    return EnergyState(
        current_energy=current,
        max_energy=maximum,
        last_updated=kwargs.pop("last_updated", T0),
        **kwargs,
    )


def test_default_policy_matches_shared_source_configuration():
    policy = DEFAULT_ENERGY_POLICY
    assert policy.base_max_energy == 100
    assert policy.regen_rate_per_minute == 1.0
    assert policy.level_bonus_per_10_levels == 10
    assert policy.vip_bonus_multiplier == 1.5
    assert policy.perfect_catch_refund == 1
    assert policy.ad_restore == 10
    assert policy.gem_refill_cost == 50


def test_max_energy_scales_by_level_and_vip_without_storage_lookup():
    assert max_energy_for_level(1) == 100
    assert max_energy_for_level(25) == 120
    assert max_energy_for_level(25, vip_active=True) == 170


def test_initialize_and_sync_max_energy_clamp_current_to_new_limit():
    state = initialize_energy(now=T0, level=30, vip_active=True)
    assert state.current_energy == state.max_energy == 180

    lowered = sync_max_energy(state, level=1, vip_active=False)
    assert lowered.current_energy == lowered.max_energy == 100


def test_regeneration_is_time_based_and_tracks_actual_restoration():
    state = _state(50)
    regenerated = regenerate_energy(state, now=T0 + timedelta(minutes=10))
    assert regenerated.current_energy == 60
    assert regenerated.total_energy_restored == 10
    assert regenerated.last_updated == T0 + timedelta(minutes=10)


def test_regeneration_accounts_for_boosted_then_base_window():
    state = _state(
        50,
        regen_multiplier=2.0,
        regen_multiplier_until=T0 + timedelta(minutes=5),
    )
    regenerated = regenerate_energy(state, now=T0 + timedelta(minutes=10))
    assert regenerated.current_energy == 65
    assert regenerated.regen_multiplier == 1.0
    assert regenerated.regen_multiplier_until is None


def test_full_energy_does_not_bank_old_regeneration_time():
    full = _state(100)
    synced = regenerate_energy(full, now=T0 + timedelta(minutes=30))
    spent = consume_energy(synced, 10, now=T0 + timedelta(minutes=30))
    one_minute_later = regenerate_energy(
        spent,
        now=T0 + timedelta(minutes=31),
    )
    assert one_minute_later.current_energy == 91


def test_consume_fails_closed_on_insufficient_energy():
    with pytest.raises(ValueError, match="not enough energy"):
        consume_energy(_state(3), 4, now=T0)


def test_infinite_energy_consumption_has_no_spend_side_effect():
    state = _state(20, infinite_until=T0 + timedelta(minutes=30))
    consumed = consume_energy(state, 10, now=T0 + timedelta(minutes=5))
    assert consumed.current_energy == 100
    assert consumed.total_energy_spent == 0


def test_restore_caps_to_max_and_accounts_only_actual_restoration():
    state = _state(95)
    restored = restore_energy(state, 20, now=T0)
    assert restored.current_energy == 100
    assert restored.total_energy_restored == 5


def test_perfect_catch_refund_uses_policy_amount():
    restored = perfect_catch_refund(_state(90), now=T0)
    assert restored.current_energy == 91
    assert restored.total_energy_restored == 1


def test_ad_restore_enforces_daily_limit_and_resets_next_utc_day():
    state = _state(
        50,
        ads_watched_today=10,
        last_ad_watch=T0 + timedelta(hours=1),
    )
    with pytest.raises(ValueError, match="daily ad energy limit"):
        restore_from_ad(state, now=T0 + timedelta(hours=2))

    next_day = restore_from_ad(state, now=T0 + timedelta(days=1))
    assert next_day.state.ads_watched_today == 1
    assert next_day.ads_remaining == 9
    # Passive regeneration fills the bar before the next-day ad claim.
    assert next_day.restored == 0


def test_source_booster_normalization_and_effects():
    restore_booster = energy_booster_from_record(
        {
            "id": "small_energy_drink",
            "name": "Small Energy Drink",
            "energy_restore": 25,
            "cost": {"coins": 500},
        }
    )
    assert restore_booster.cost == {"coins": 500}
    assert apply_booster(_state(50), restore_booster, now=T0).current_energy == 75

    infinite = EnergyBoosterSpec(
        id="infinite",
        name="Infinite",
        infinite_duration_minutes=60,
    )
    infinite_state = apply_booster(_state(20), infinite, now=T0)
    assert infinite_state.current_energy == 100
    assert infinite_state.infinite_until == T0 + timedelta(minutes=60)

    regen = EnergyBoosterSpec(
        id="double",
        name="Double",
        regen_multiplier=2.0,
        duration_minutes=30,
    )
    regen_state = apply_booster(_state(20), regen, now=T0)
    assert regen_state.regen_multiplier == 2.0
    assert regen_state.regen_multiplier_until == T0 + timedelta(minutes=30)


def test_booster_rejects_ambiguous_multiple_effects():
    with pytest.raises(ValueError, match="exactly one effect"):
        EnergyBoosterSpec(
            id="bad",
            name="Bad",
            energy_restore=10,
            infinite_duration_minutes=10,
        )


@pytest.mark.parametrize(
    "state",
    [
        EnergyState(
            current_energy=50,
            max_energy=100,
            last_updated=T0,
            regen_multiplier=2.0,
            regen_multiplier_until=T0 + timedelta(minutes=10),
        ),
        EnergyState(
            current_energy=100,
            max_energy=100,
            last_updated=T0,
            infinite_until=T0 + timedelta(minutes=10),
        ),
    ],
)
def test_status_projection_is_deterministic_and_nonmutating(state):
    status = energy_status(state, now=T0 + timedelta(minutes=5))
    assert status.state is not state
    assert status.minutes_to_full >= 0
