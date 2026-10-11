"""Forty-era adaptive NPC simulation: real brain budgets, no ghost workers.

All tests run actual ProductSession with sparse regional and local resources.
The 16k remote census is not represented as 16k individually simulated minds.
"""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_era_runtime import ERA_LEVELS
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_npc_era_population import (
    FIDELITY_MODES, active_brain_budget, select_active_brains,
    ambient_impressions, fidelity_report, era_budget,
    population_report, population_save, population_restore,
    validate_population, _hash,
)
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, step_product, product_save,
    product_restore, validate_product,
)
from skeleton.game.generation.original_world_product_render import (
    scene, svg_render, ascii_render, ppm_render,
)
from skeleton.game.generation.original_world_product_cli import main


def original(era="digital-network", fidelity="balanced"):
    law = living_for(0, "puzzle", "lattice", "trophic", "sandbox")
    return create_product(law.index, era=era, npc_fidelity=fidelity)


def turn(session):
    return step_product(session, ProductAction("causal", "end_turn"))


def test_every_one_of_40_eras_exposes_finite_explicit_census_and_cpu_budgets():
    assert len(ERA_LEVELS) == 40
    assert set(FIDELITY_MODES) == {"economy", "balanced", "vivid", "unrestricted"}
    for era in ERA_LEVELS:
        b = era_budget(era)
        assert 1 <= b.full_npc_limit <= 32
        assert 0 <= b.district_limit <= 64
        assert 0 <= b.background_limit <= 16384
        assert b.district_updates <= 8
        assert 0 <= b.render_budget <= 64
        assert 1 <= active_brain_budget(era, "economy") <= 3
        assert active_brain_budget(era, "economy") <= active_brain_budget(era, "balanced")
        assert active_brain_budget(era, "balanced") <= active_brain_budget(era, "vivid")
        assert active_brain_budget(era, "vivid") <= active_brain_budget(era, "unrestricted")


def test_local_count_increases_with_technology_but_remote_counts_do_not_create_bodies():
    earliest = original("primordial-earth")
    middle = original("iron-age")
    late = original("digital-network")
    latest = original("cosmic-epoch")
    real = [len(s.society.inhabitants) for s in (earliest, middle, late, latest)]
    assert real == [1, era_budget("iron-age").full_npc_limit - 2,
                    era_budget("digital-network").full_npc_limit - 2, 30]
    assert real == sorted(real)
    assert earliest.population.districts == ()
    assert latest.population.districts
    info = population_report(latest.population, real[-1])
    assert info["regional_aggregated_residents"] == 16384
    assert info["full_personality_and_physics_NPCs"] == 30
    assert len(latest.cognition.minds) == 30


@pytest.mark.parametrize("mode,cap", [
    ("economy", 3), ("balanced", 7), ("vivid", 16),
    ("unrestricted", 30),
])
def test_four_fidelity_modes_schedule_exactly_the_allowed_number_of_thinking_bodies(mode, cap):
    world = original("cosmic-epoch", mode)
    active = select_active_brains(
        world.population, world.society, world.terrain,
        world.cognition, preset=mode,
    )
    assert len(active) == cap
    assert active == tuple(sorted(set(active)))
    assert all(0 <= ident < 30 for ident in active)
    after, receipt = turn(world)
    assert len(after.society.inhabitants) == 30
    assert sum(m.decisions for m in after.cognition.minds) == cap
    assert f"{cap} full cognitive decisions" in " ".join(receipt.changes)
    assert after.population.day == after.society.tick == 1
    assert product_restore(product_save(after)) == after


def test_unscheduled_people_remain_actual_physical_residents_and_cannot_mint_work():
    world = original("near-future", "economy")
    awake = set(select_active_brains(
        world.population, world.society, world.terrain, world.cognition,
        preset="economy",
    ))
    before = {p.id: p for p in world.society.inhabitants}
    after, _ = turn(world)
    for citizen in after.society.inhabitants:
        if citizen.id not in awake:
            prior = before[citizen.id]
            assert (citizen.x, citizen.y) == (prior.x, prior.y)
            assert citizen.cargo == prior.cargo
            assert citizen.experience == prior.experience
            assert citizen.hunger >= prior.hunger
            assert after.cognition.minds[citizen.id].decisions == 0
            assert after.cognition.minds[citizen.id].memories == ()


def test_life_threatening_hunger_has_priority_over_camera_and_idle_plans():
    world = original("near-future", "economy")
    distant = world.society.inhabitants[-1]
    people = list(world.society.inhabitants)
    people[-1] = replace(distant, hunger=13, health=4)
    world = replace(world, society=replace(world.society,
                                           inhabitants=tuple(people)))
    active = select_active_brains(
        world.population, world.society, world.terrain, world.cognition,
        preset="economy")
    assert distant.id in active
    after, _ = turn(world)
    assert after.cognition.minds[distant.id].decisions == 1


def test_idle_towns_rotate_thinkers_without_starving_faraway_agents_of_all_attention():
    world = original("near-future", "economy")
    observed = set()
    for _ in range(12):
        active = select_active_brains(
            world.population, world.society, world.terrain, world.cognition,
            preset="economy",
        )
        observed.update(active)
        world, _ = turn(world)
    assert len(observed) > 3
    assert len(observed) <= len(world.society.inhabitants)
    assert sum(m.decisions for m in world.cognition.minds) <= 36


def test_actual_populated_world_remains_same_after_save_reload_multiple_lod_days():
    def run():
        state = original("steam-age", "vivid")
        for _ in range(5):
            state, _ = turn(state)
        return state
    first, second = run(), run()
    assert first == second
    assert product_save(first) == product_save(second)
    assert first.population.day == first.cognition.day == 5
    assert product_restore(product_save(first)) == first


def test_synthetic_background_visuals_have_no_individual_work_rights_or_duplication():
    world = original("digital-network")
    depots = ambient_impressions(
        world.population, world.terrain, radius=15, max_visible=24)
    assert len(depots) <= 24
    assert depots == ambient_impressions(
        world.population, world.terrain, radius=15, max_visible=24)
    assert len({(r["x"], r["y"]) for r in depots}) == len(depots)
    assert all(r["is_simplified_visual_proxy"] and
               not r["has_individual_cognition"] and not r["can_vote"] and
               not r["can_use_resources"] for r in depots)
    drawn = scene(world.terrain, world.society, radius=15,
                  population=world.population)
    assert len(drawn["people"]) == len(world.society.inhabitants)
    assert len(drawn["ambient"]) <= 24
    svg = svg_render(world.terrain, world.society, radius=15,
                     population=world.population)
    assert svg.count('data-agent-kind="render-only"') == len(drawn["ambient"])
    assert ppm_render(world.terrain, world.society, radius=8,
                      population=world.population).startswith(b"P6")
    assert "R" in ascii_render(world.terrain, world.society, radius=15,
                               population=world.population)


def test_passive_survival_never_mints_food_even_under_massive_background_census():
    world = original("cosmic-epoch", "economy")
    stock = world.terrain.provisions
    remote_initial = sum(d.pantry for d in world.population.districts)
    world, _ = turn(world)
    assert world.terrain.provisions <= stock + 3 * 24
    assert sum(d.pantry for d in world.population.districts) <= remote_initial
    assert len(world.cognition.minds) == 30
    assert len(world.population.districts) <= 64


def test_old_v2_game_save_and_prior_population_snapshot_are_migrated_safely():
    state = original("steam-age")
    envelope = population_save(state.population)
    envelope["payload"].pop("fidelity")
    envelope["checksum"] = _hash(envelope["payload"])
    restored = population_restore(envelope, state.society, state.terrain)
    assert restored.fidelity == "balanced"
    assert restored == state.population
    no_era = create_product(living_for(
        0, "puzzle", "lattice", "trophic", "sandbox").index)
    assert no_era.population is None
    assert product_restore(product_save(no_era)) == no_era


def test_fidelity_configuration_rejects_malformed_or_fake_brain_allocation():
    world = original("near-future", "economy")
    fake = replace(world.population, fidelity="unbounded-magical")
    with pytest.raises(FoundationError):
        validate_population(fake, world.society, world.terrain)
    with pytest.raises(FoundationError):
        select_active_brains(world.population, world.society,
                             world.terrain, world.cognition,
                             preset="infinite")
    with pytest.raises(FoundationError):
        ambient_impressions(world.population, world.terrain,
                            radius=8, max_visible=100_000)
    with pytest.raises(FoundationError):
        create_product(living_for(0, "puzzle", "lattice",
                                  "trophic", "sandbox").index,
                       npc_fidelity="economy")


def test_cli_exposes_fidelity_selection_without_overwriting_loaded_saves(capsys, tmp_path):
    save = tmp_path / "npc-era-fidelity.json"
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--system", "trophic", "--arc", "sandbox",
        "--era", "iron-age", "--npc-fidelity", "economy",
        "--actions-json", '[{"layer":"causal","verb":"end_turn"}]',
        "--save", str(save), "--population-report",
    ]) == 0
    packet = json.loads(capsys.readouterr().out)
    rp = packet["product"]["regional_population"]
    assert rp["hardware_fidelity"]["preset"] == "economy"
    assert rp["hardware_fidelity"]["maximum_individual_brain_decisions_per_turn"] == 3
    assert product_restore(save.read_text()).population.fidelity == "economy"
