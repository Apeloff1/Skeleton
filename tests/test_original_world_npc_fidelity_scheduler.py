"""Prove meaningful era LOD, continuous bodies, conservation and real census activation."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_npc_era_population import (
    active_brain_budget, select_active_brains, population_report,
    ambient_impressions, tuning, era_budget, validate_population,
)
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, product_save, product_restore,
    step_product, validate_product,
)
from skeleton.game.generation.original_world_product_cli import parse_command, main
from skeleton.game.generation.original_world_product_terrain import cell_at


def game(era="interstellar", preset="balanced"):
    law = living_for(0, "puzzle", "lattice", "trophic", "sandbox")
    return create_product(law.index, era=era, npc_fidelity=preset)


def action(s, layer, verb, **params):
    return step_product(s, ProductAction(layer, verb, **params))[0]


def test_era_profile_scales_real_npc_capacity_without_full_brain_cost_for_every_body():
    era = "interstellar"
    assert era_budget(era).background_limit == 16384
    state = game()
    assert len(state.society.inhabitants) == 30
    assert active_brain_budget(era, "economy") == 3
    assert active_brain_budget(era, "balanced") == 7
    assert active_brain_budget(era, "vivid") == 16
    assert active_brain_budget(era, "unrestricted") == 32
    assert tuning(era, "economy")[0] <= tuning(era, "balanced")[0]
    assert tuning(era, "balanced")[0] <= tuning(era, "vivid")[0]


@pytest.mark.parametrize("preset,limit", [
    ("economy", 3), ("balanced", 7),
    ("vivid", 16), ("unrestricted", 30),
])
def test_real_individual_brain_budget_applies_to_actual_turns(preset, limit):
    initial = game(preset=preset)
    roster = initial.society.inhabitants
    selected = select_active_brains(
        initial.population, initial.society, initial.terrain, initial.cognition,
        preset=preset,
    )
    assert len(selected) == limit
    after, receipt = step_product(initial, ProductAction("causal", "end_turn"))
    assert sum(m.decisions > 0 for m in after.cognition.minds) == limit
    assert sum(m.decisions == 0 for m in after.cognition.minds) == 30-limit
    assert all(
        before.x == post.x and before.y == post.y
        for before, post in zip(roster, after.society.inhabitants)
        if before.id not in selected
    )
    assert after.society.tick == after.cognition.day == after.population.day == 1
    assert "full cognitive decisions" in " ".join(receipt.changes)
    assert product_restore(product_save(after)) == after


def test_priority_protects_actually_hungry_resident_outside_player_camera():
    s = game(preset="economy")
    last = s.society.inhabitants[-1]
    society = replace(s.society, inhabitants=(
        *s.society.inhabitants[:-1],
        replace(last, hunger=19, health=4),
    ))
    state = replace(s, society=society)
    selected = select_active_brains(
        state.population, state.society, state.terrain, state.cognition,
        preset="economy")
    assert last.id in selected
    after = action(state, "causal", "end_turn")
    assert after.cognition.minds[last.id].decisions == 1


def test_inactive_bodies_never_gain_teleportation_fake_education_or_materials():
    s = game(preset="economy")
    before = tuple((p.x, p.y, p.experience, p.cargo)
                   for p in s.society.inhabitants)
    selected = select_active_brains(
        s.population, s.society, s.terrain, s.cognition, preset="economy")
    post = action(s, "causal", "end_turn")
    for person in post.society.inhabitants:
        if person.id not in selected:
            x, y, experience, cargo = before[person.id]
            assert (person.x, person.y, person.experience, person.cargo) == (
                x, y, experience, cargo)
    assert post.population.food_consumed >= 0


def test_budget_change_never_edits_people_materials_census_or_memory():
    state = game()
    census = sum(d.population for d in state.population.districts)
    old_roster, old_brains, old_physical = (
        state.society, state.cognition, state.terrain
    )
    state = action(state, "population", "set_detail", option="economy")
    assert state.population.fidelity == "economy"
    assert sum(d.population for d in state.population.districts) == census
    assert state.society == old_roster
    assert state.cognition == old_brains
    assert state.terrain == old_physical
    state = action(state, "population", "set_detail", option="unrestricted")
    assert state.population.fidelity == "unrestricted"
    assert product_restore(product_save(state)) == state
    with pytest.raises(FoundationError):
        action(state, "population", "set_detail", option="imaginary")


def test_regional_physical_immigration_is_real_body_mind_and_deducted_census():
    s = game("early-industrial")
    remote = s.population.districts[0]
    # Physical arrival fixture: test transfers one actual census resident,
    # rather than teleporting player as part of recruitment itself.
    local = replace(s.terrain, position=(remote.x, remote.y))
    s = replace(s, terrain=local)
    old_total = len(s.society.inhabitants) + sum(
        d.population for d in s.population.districts)
    before = s.society.inhabitants
    s, receipt = step_product(
        s, ProductAction("population", "recruit", target=0))
    assert len(s.society.inhabitants) == len(before) + 1
    assert s.society.inhabitants[-1].id == len(before)
    assert s.society.inhabitants[-1].x == remote.x
    assert s.society.inhabitants[-1].y == remote.y
    assert not cell_at(s.terrain, remote.x, remote.y).blocking
    assert len(s.cognition.minds) == len(s.society.inhabitants)
    assert s.cognition.households.ages[-1] == 24
    assert s.population.districts[0].population == remote.population - 1
    assert s.population.migrations[-1].citizen == len(before)
    after_total = len(s.society.inhabitants) + sum(
        d.population for d in s.population.districts)
    assert old_total == after_total
    assert "census" in " ".join(receipt.changes)
    assert validate_product(s)
    assert product_restore(product_save(s)) == s


def test_regional_recruitment_requires_player_presence_and_real_available_slots():
    s = game("paleolithic")
    with pytest.raises(FoundationError):
        action(s, "population", "recruit", target=0)
    assert not s.population.migrations
    district = s.population.districts[0]
    located = replace(s, terrain=replace(s.terrain,
                                         position=(district.x, district.y)))
    authorized = action(located, "population", "recruit", target=0)
    assert len(authorized.population.migrations) == 1
    # The next migration reaches the era's detailed-brain limit.
    second = action(authorized, "population", "recruit", target=0)
    assert len(second.population.migrations) == 2
    with pytest.raises(FoundationError):
        action(second, "population", "recruit", target=0)


def test_honest_visual_impressions_are_budgeted_and_not_fake_individual_agents():
    s = game("interstellar", preset="economy")
    badges = ambient_impressions(s.population, s.terrain, radius=20)
    assert len(badges) <= 64
    assert all(x["is_simplified_visual_proxy"] for x in badges)
    assert all(not x["has_individual_cognition"] and not x["can_vote"]
               and not x["can_use_resources"] for x in badges)
    report = population_report(s.population, len(s.society.inhabitants))
    assert report["regional_aggregated_residents"] == 16384
    assert len(badges) <= report["visible_proxy_budget"] * 2
    assert report["total_census"] >= 16384


def test_cli_era_npc_profile_and_portable_save_roundtrip(capsys, tmp_path):
    path = tmp_path / "future.json"
    assert parse_command("population recruit 0", (0, 0)).verb == "recruit"
    assert parse_command("population set_detail economy", (0, 0)).option == "economy"
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--system", "trophic", "--arc", "sandbox",
        "--era", "interstellar", "--npc-fidelity", "economy",
        "--actions-json", '[{"layer":"population","verb":"set_detail",'
                          '"option":"vivid"},{"layer":"causal","verb":"end_turn"}]',
        "--population-report", "--save", str(path),
    ]) == 0
    printed = json.loads(capsys.readouterr().out)
    report = printed["product"]["regional_population"]
    assert report["detail_mode"] == "vivid"
    assert report["regional_aggregated_residents"] == 16384
    assert report["full_local_brain_budget_per_turn"] == 16
    assert main(["--load", str(path), "--population-report"]) == 0
    loaded = json.loads(capsys.readouterr().out)
    assert loaded["product"]["regional_population"]["detail_mode"] == "vivid"
