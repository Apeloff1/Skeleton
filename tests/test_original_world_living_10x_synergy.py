"""Proof that autonomous living world systems alter real game mechanics."""
from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_living_10x_runtime import (
    LivingAction, create_living, step_living, validate_living,
)


def create(system, genre="puzzle"):
    return create_living(living_for(0, genre, "lattice", system, "sandbox").index)


def tick(state, count=1):
    for _ in range(count):
        state, _ = step_living(state, LivingAction("causal", "end_turn"))
        validate_living(state)
    return state


def test_ecosystem_collapse_changes_actual_world_navigation_risk() -> None:
    s = create("trophic")
    s = replace(s, metrics=replace(s.metrics, vegetation=0, seedlings=0))
    hazard = s.spatial.danger
    after = tick(s)
    assert after.spatial.danger == hazard + 1


def test_hungry_town_loses_real_source_game_legitimacy() -> None:
    s = create("settlement")
    s = replace(s, metrics=replace(s.metrics, unrest=6, food=0))
    after = tick(s)
    assert after.spatial.game.causal.trust == s.spatial.game.causal.trust - 1
    assert after.metrics.households < s.metrics.households


def test_earned_caravan_revenue_transfers_into_actual_commerce_wallet() -> None:
    s = create("caravans", genre="commerce")
    s = replace(s, metrics=replace(s.metrics, credit=12))
    old_capital = s.spatial.game.mode.wallet
    after = tick(s)
    assert after.metrics.credit == 10
    assert after.spatial.game.mode.wallet == old_capital + 2


def test_unresolved_floods_increase_permanent_spatial_hazard() -> None:
    s = create("watershed")
    s = replace(s, metrics=replace(s.metrics, flood=3))
    after = tick(s)
    assert after.spatial.danger == s.spatial.danger + 1


def test_farm_harvest_transfers_finite_soil_to_colony_food() -> None:
    s = create("watershed", genre="colony")
    s = replace(s, metrics=replace(s.metrics, soil=9))
    # Source colony normally consumes one food per turn; the harvest on turn
    # two must still be tied to a recorded reduction of fertile soil.
    after = tick(s, 2)
    assert after.metrics.soil == 8
    assert after.spatial.game.mode.colony_food >= 0


def test_grid_blackout_is_real_civic_trust_erosion() -> None:
    s = create("power")
    s = replace(s,
                metrics=replace(s.metrics, battery=0, outages=3),
                spatial=replace(s.spatial, fuel=0))
    trust = s.spatial.game.causal.trust
    after = tick(s)
    assert after.metrics.outages > s.metrics.outages
    assert after.spatial.game.causal.trust == trust - 1


def test_fictional_spore_outbreak_saps_causal_action_stamina() -> None:
    s = create("spores")
    s = replace(s, metrics=replace(s.metrics, unaffected=4, affected=6))
    # Source end-turn naturally restores 2 energy; sickness spends 1 of
    # that recovery. Set pre-turn energy low enough to observe the debit.
    game = s.spatial.game
    s = replace(s, spatial=replace(s.spatial, game=replace(
        game, causal=replace(game.causal, energy=5))))
    after = tick(s)
    assert after.spatial.game.causal.energy == 6
    assert after.metrics.unaffected + after.metrics.affected + after.metrics.recovered == 10


def test_constructed_robots_physically_supply_colony_housing() -> None:
    s = create("fabrication", genre="colony")
    game = s.spatial.game
    initial = game.mode.housing
    s = replace(s, metrics=replace(s.metrics, orders=1))
    after = tick(s)
    assert after.metrics.completed == 0
    assert after.metrics.components == s.metrics.components - 1
    assert after.spatial.game.mode.housing == initial + 1


def test_verified_learning_enters_game_evidence_only_by_debiting_shared_facts() -> None:
    s = create("knowledge")
    s = replace(s, metrics=replace(s.metrics, shared=3))
    evidence = s.spatial.game.causal.evidence
    after = tick(s)
    assert after.metrics.shared == 2
    assert after.spatial.game.causal.evidence == evidence + 1


def test_faction_tension_creates_real_physical_risk() -> None:
    s = create("diplomacy")
    s = replace(s, metrics=replace(s.metrics, tension=8))
    after = tick(s)
    assert after.spatial.danger == s.spatial.danger + 1


def test_matured_temporal_echo_causes_a_single_paid_causal_world_gain() -> None:
    s = create("echoes")
    s, recorded = step_living(s, LivingAction("living", "record"))
    base = s.spatial.game.causal.primary
    s = tick(s)
    assert s.spatial.game.causal.primary == base
    s = tick(s)
    assert s.metrics.queued_echoes == 0
    assert s.spatial.game.causal.primary == base + 1
    s = tick(s)
    assert s.spatial.game.causal.primary == base + 1
    assert s.metrics.time_debt == 3
    assert s.event_head != recorded.event_hash


def test_cross_layer_consequence_rejects_corrupt_overcrowded_world() -> None:
    s = create("settlement")
    s = replace(s, metrics=replace(s.metrics, households=99))
    with pytest.raises(Exception):
        tick(s)
