"""Era-aware physically grounded NPC populations; measured quality, not crowd inflation."""
from __future__ import annotations
from dataclasses import replace
import json
import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_era_runtime import ERA_LEVELS
from skeleton.game.generation.original_world_npc_era_population import (
    MAX_POPULATION, SCHEMA, District, Caravan,
    era_budget, permitted_roles, create_era_population,
    dispatch_food, tick_population, validate_population,
    population_save, population_restore, population_report,
)
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, step_product, product_save, product_restore,
)
from skeleton.game.generation.original_world_product_render import (
    scene, svg_render, ascii_render, ppm_render,
)
from skeleton.game.generation.original_world_product_cli import (
    main, parse_command,
)


def product(era="early-industrial", inhabitants=None):
    index = living_for(0, "puzzle", "lattice", "trophic", "sandbox").index
    return create_product(index, era=era, inhabitants=inhabitants)


def step(state, verb="end_turn", layer="causal", **kwargs):
    return step_product(state, ProductAction(layer, verb, **kwargs))[0]


def total_food(state):
    assert state.population is not None
    return (
        state.terrain.provisions
        + sum(d.pantry for d in state.population.districts)
        + sum(c.food for c in state.population.caravans
              if c.status == "travelling")
        + state.population.food_consumed
    )


def test_all_forty_authored_eras_have_bounded_real_fidelity_budgets():
    assert len(ERA_LEVELS) == 40
    for era, technology in ERA_LEVELS.items():
        b = era_budget(era)
        assert b.technology == technology
        assert 1 <= b.full_npc_limit <= 32
        assert 0 <= b.district_limit <= 64
        assert 0 <= b.background_limit <= MAX_POPULATION
        assert 0 <= b.district_updates <= 8
        assert 0 <= b.render_budget <= 64
        assert b.caravan_speed >= 1
    assert era_budget("paleolithic").background_limit < era_budget("bronze-age").background_limit
    assert era_budget("bronze-age").background_limit < era_budget("early-industrial").background_limit
    assert era_budget("early-industrial").background_limit < era_budget("interstellar").background_limit
    assert era_budget("interstellar").full_npc_limit <= 32
    assert era_budget("primordial-earth").background_limit == 0
    assert era_budget("early-life").background_limit == 0


def test_era_actual_local_npc_pool_grows_while_protecting_birth_slots():
    early = product("paleolithic")
    modern = product("electrical-age")
    future = product("interstellar")
    assert len(early.society.inhabitants) < len(modern.society.inhabitants)
    assert len(modern.society.inhabitants) < len(future.society.inhabitants)
    assert len(future.society.inhabitants) == 30
    assert era_budget("interstellar").full_npc_limit == 32
    assert len(future.population.districts) == 50
    assert sum(d.population for d in future.population.districts) == 16384
    assert len(future.cognition.minds) == len(future.society.inhabitants)
    assert len(future.cognition.minds) != 16384


def test_stone_age_citizens_cannot_spawn_future_engineers_or_be_assigned_one():
    early = product("paleolithic")
    assert all(p.profession in permitted_roles("paleolithic")
               for p in early.society.inhabitants)
    assert "engineer" not in permitted_roles("paleolithic")
    with pytest.raises(FoundationError):
        step(early, "assign", "studio", target=0, option="engineer")
    assert "engineer" in permitted_roles("interstellar")
    with pytest.raises(FoundationError):
        product("paleolithic", inhabitants=32)


def test_era_population_is_finite_and_anchored_to_walkable_real_terrain():
    s = product("early-industrial")
    p = s.population
    b = era_budget(p.era)
    assert len(p.districts) == b.district_limit
    assert sum(d.population + d.deaths for d in p.districts) == b.background_limit
    assert len({(d.x, d.y) for d in p.districts}) == len(p.districts)
    from skeleton.game.generation.original_world_product_terrain import cell_at
    assert all(not cell_at(s.terrain, d.x, d.y).blocking for d in p.districts)
    validate_population(p, s.society, s.terrain)


def test_one_era_turn_only_services_capped_districts_not_all_remote_brains():
    s = product("interstellar")
    before = s.population
    s = step(s)
    assert s.population.day == 1
    assert s.population.updates == era_budget("interstellar").district_updates
    assert s.population.updates <= 8
    assert sum(d.last_day == 1 for d in s.population.districts) == s.population.updates
    assert sum(d.last_day == 0 for d in s.population.districts) > 0
    assert s.society.tick == s.cognition.day == s.population.day
    assert all(0 <= d.pantry <= 2000000 for d in s.population.districts)


def test_sparse_regional_ticks_are_reproducible_for_real_economies():
    def evolve():
        s = product("digital-network")
        # Four days exercise remote ration updates before any local
        # autonomously hungry resident consumes separate town supplies.
        for _ in range(4):
            s = step(s)
        return s
    a, b = evolve(), evolve()
    assert a == b
    assert product_save(a) == product_save(b)
    assert a.population.updates <= 4 * era_budget("digital-network").district_updates
    assert a.population.food_consumed > 0
    assert total_food(a) == total_food(product("digital-network"))


def test_food_transport_is_escrowed_at_departure_then_delayed_until_arrival():
    s = product("paleolithic")
    depot_food = s.terrain.provisions
    district_before = s.population.districts[0].pantry
    beginning = total_food(s)
    s = step(s, "dispatch_food", "population",
             target=0, option="to-region", amount=2)
    caravan = s.population.caravans[-1]
    assert caravan.status == "travelling"
    assert s.terrain.provisions == depot_food - 2
    assert s.population.districts[0].pantry == district_before
    # Local full-depth people may actually eat from separate food stocks
    # during a long caravan journey; regional trade itself never mints food.
    assert total_food(s) <= beginning
    for _ in range(caravan.arrives):
        s = step(s)
    assert s.population.caravans[-1].status == "delivered"
    assert total_food(s) == beginning
    assert s.population.food_consumed > 0


def test_importing_remote_food_never_mints_or_teleports_goods():
    s = product("digital-network")
    prior_food = s.terrain.provisions
    before = total_food(s)
    s = step(s, "dispatch_food", "population",
             target=0, option="to-player", amount=3)
    assert s.population.districts[0].pantry == (
        product("digital-network").population.districts[0].pantry - 3
    )
    assert s.terrain.provisions == prior_food
    arriving = s.population.caravans[0].arrives
    for _ in range(arriving):
        s = step(s)
    assert s.population.caravans[0].status == "delivered"
    assert s.population.caravans[0].status == "delivered"
    assert s.terrain.provisions >= 0
    assert total_food(s) <= before
    assert product_restore(product_save(s)) == s


def test_import_stays_escrowed_when_local_warehouse_is_full():
    s = product("paleolithic")
    s = step(s, "dispatch_food", "population",
             target=0, option="to-player", amount=1)
    s = replace(s, terrain=replace(s.terrain, provisions=1000))
    until = s.population.caravans[0].arrives
    for _ in range(until):
        s = step(s)
    assert s.population.caravans[0].status == "travelling"
    assert s.terrain.provisions == 1000
    s = replace(s, terrain=replace(s.terrain, provisions=995))
    s = step(s)
    assert s.population.caravans[0].status == "delivered"
    assert s.terrain.provisions >= 996


def test_districts_eventually_experience_real_shortages_and_census_mortality():
    s = product("paleolithic")
    district = s.population.districts[0]
    # Explicit adversarial shortage fixture: no remote pantry, no free feed.
    first = replace(district, pantry=0)
    s = replace(s, population=replace(s.population,
                                      districts=(first, *s.population.districts[1:])))
    original = first.population
    for _ in range(40):
        s = step(s)
    d = s.population.districts[0]
    assert d.population < original
    assert d.deaths > 0
    assert d.population + d.deaths == original
    assert s.population.total_deaths >= d.deaths
    assert d.hardship > 0


def test_forged_census_clock_materials_and_save_sha_fail_closed():
    s = product("steam-age")
    invalid = replace(s.population, day=999)
    with pytest.raises(FoundationError):
        validate_population(invalid, s.society, s.terrain)
    bad_d = replace(s.population.districts[0], population=999999)
    corrupted = replace(s.population, districts=(
        bad_d, *s.population.districts[1:],
    ))
    with pytest.raises(FoundationError):
        validate_population(corrupted, s.society, s.terrain)
    persisted = population_save(s.population)
    assert population_restore(persisted, s.society, s.terrain) == s.population
    persisted["payload"]["districts"][0]["pantry"] = 100000
    with pytest.raises(FoundationError):
        population_restore(persisted, s.society, s.terrain)


def test_legacy_game_save_retains_old_12_npc_behavior_with_no_phantom_cohorts():
    normal = create_product(living_for(
        0, "puzzle", "lattice", "trophic", "sandbox",
    ).index)
    assert len(normal.society.inhabitants) == 12
    assert normal.population is None
    assert product_restore(product_save(normal)) == normal
    normal = step(normal)
    assert product_restore(product_save(normal)) == normal


def test_era_region_render_badges_are_distinct_from_real_individual_npcs():
    s = product("paleolithic")
    view = scene(s.terrain, s.society, radius=20, population=s.population)
    assert len(view["districts"]) > 0
    assert len(view["people"]) == len(s.society.inhabitants)
    assert sum(d["census"] for d in view["districts"]) > len(view["people"])
    svg = svg_render(s.terrain, s.society, radius=20, population=s.population)
    assert 'fill="#c39bfa"' in svg
    assert "Regional census" in svg
    output = ppm_render(s.terrain, s.society, radius=20, scale=1,
                        population=s.population)
    assert output.startswith(b"P6")
    chars = ascii_render(s.terrain, s.society, radius=20,
                         population=s.population)
    assert "R" in chars and "@" in chars
    assert len(view["districts"]) <= era_budget("paleolithic").render_budget


def test_cli_era_report_and_real_transport_commands_and_loaded_save(tmp_path, capsys):
    save = tmp_path / "era.json"
    assert parse_command(
        "population dispatch_food 0 to-region 2", (0, 0)
    ) == ProductAction(
        "population", "dispatch_food", amount=2,
        target=0, option="to-region",
    )
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--system", "trophic", "--arc", "sandbox",
        "--era", "near-future",
        "--actions-json", '[{"layer":"population","verb":"dispatch_food",'
                          '"target":0,"option":"to-region","amount":2},'
                          '{"layer":"causal","verb":"end_turn"}]',
        "--population-report", "--save", str(save),
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["product"]["regional_population"]["era"] == "near-future"
    assert output["product"]["regional_population"]["districts"] > 0
    assert output["product"]["regional_population"]["caravans"]
    assert save.exists()
    assert main(["--load", str(save), "--population-report"]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["product"]["regional_population"]["total_census"] > 32
    assert main(["--inventory"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert len(catalog["era_population_capabilities"]) == 40
