"""Measured-invariant tests for all supported target consoles, PC eras and genres.

These are conservative design budgets: no claim of statistically measured
above-market NPC means, or native executable compatibility for consoles.
"""
from __future__ import annotations
from dataclasses import replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_era_runtime import ERA_LEVELS
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_npc_platform_profiles import (
    PROFILE_SCHEMA, PC_GENERATIONS, PLATFORM_TIER, GENRE_BUDGETS,
    DEFAULT_PC_GENERATION, TIERS, plan_population, platform_inventory,
)
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, validate_product, step_product,
    product_save, product_restore,
)
from skeleton.game.generation.original_world_npc_era_population import (
    create_era_population, population_report, population_restore,
    population_save, active_brain_budget, ambient_impressions,
    select_active_brains, validate_population,
)
from skeleton.game.generation.world_styling import HARDWARE_TARGETS
from skeleton.game.generation.original_world_play_forms import FORM_BY_ID
from skeleton.game.generation.original_world_product_cli import main


def game(*, era="interstellar", hardware="pc-windows", genre="colony",
         generation=None, preset="balanced", count=None):
    law = living_for(0, genre, "lattice", "trophic", "sandbox")
    return create_product(
        law.index, era=era, inhabitants=count,
        hardware_target=hardware, pc_generation=generation,
        npc_fidelity=preset,
    )


def test_exhaustive_41_original_console_pc_homebrew_targets_are_explicit():
    assert set(HARDWARE_TARGETS) == set(PLATFORM_TIER)
    assert len(HARDWARE_TARGETS) == 41
    assert set(FORM_BY_ID) == set(GENRE_BUDGETS)
    assert len(FORM_BY_ID) == 10
    assert len(PC_GENERATIONS) == 9
    assert set(platform_inventory()) == set(HARDWARE_TARGETS)
    assert len(TIERS) >= 8


def test_all_16400_era_console_genre_combinations_are_bounded_and_no_fictitious_crowds():
    for era in ERA_LEVELS:
        for platform in HARDWARE_TARGETS:
            for genre in FORM_BY_ID:
                p = plan_population(era, platform, genre)
                assert p.schema == PROFILE_SCHEMA
                assert 1 <= p.local_limit <= 24
                assert 1 <= p.starting_locals <= p.local_limit
                assert p.local_limit - p.starting_locals <= 2
                assert 0 <= p.regional_limit <= 144
                assert 0 <= p.district_limit <= 8
                assert 1 <= p.brain_limit <= min(14, p.local_limit)
                assert 0 <= p.visual_proxy_limit <= 10
                assert 0 <= p.district_update_limit <= 3
                assert p.district_limit == 0 if p.regional_limit == 0 else p.district_limit >= 1


def test_all_3600_additional_pc_era_generation_genre_profiles_are_explicit():
    for era in ERA_LEVELS:
        for gen in PC_GENERATIONS:
            for genre in FORM_BY_ID:
                p = plan_population(
                    era, "pc-windows", genre, pc_generation=gen)
                assert p.pc_generation == gen
                assert 1 <= p.local_limit <= 24
                assert p.regional_limit <= 144
    assert DEFAULT_PC_GENERATION == "2020s-integrated"


def test_reference_targets_raise_local_density_by_hardware_without_fake_16k_census():
    nes = plan_population("interstellar", "nes", "colony")
    ps2 = plan_population("interstellar", "playstation-2", "colony")
    ps5 = plan_population("interstellar", "playstation-5", "colony")
    pc = plan_population(
        "interstellar", "pc-windows", "colony",
        pc_generation="2020s-highend")
    assert nes.local_limit == 3
    assert ps2.local_limit == 10
    assert ps5.local_limit == 24
    assert pc.local_limit == 24
    assert nes.regional_limit < ps2.regional_limit < ps5.regional_limit
    assert pc.regional_limit == 144
    assert pc.district_limit == 8
    assert pc.brain_limit == 14
    assert pc.starting_locals == 22


def test_genre_changes_character_focus_more_than_technology_skins():
    colony = plan_population("interstellar", "pc-windows", "colony")
    puzzle = plan_population("interstellar", "pc-windows", "puzzle")
    racing = plan_population("interstellar", "pc-windows", "racing")
    stealth = plan_population("interstellar", "pc-windows", "stealth")
    rhythm = plan_population("interstellar", "pc-windows", "rhythm")
    assert racing.local_limit < stealth.local_limit < colony.local_limit
    assert rhythm.regional_limit < puzzle.regional_limit < colony.regional_limit
    assert colony.regional_limit <= 144
    assert puzzle.visual_proxy_limit <= colony.visual_proxy_limit


def test_world_technology_limits_population_even_on_fast_pc():
    early = plan_population("paleolithic", "pc-windows", "colony",
                            pc_generation="2020s-highend")
    bronze = plan_population("bronze-age", "pc-windows", "colony",
                             pc_generation="2020s-highend")
    modern = plan_population("interstellar", "pc-windows", "colony",
                             pc_generation="2020s-highend")
    assert early.local_limit < bronze.local_limit < modern.local_limit
    assert early.regional_limit < bronze.regional_limit < modern.regional_limit
    assert early.brain_limit <= modern.brain_limit


def test_primitive_geological_worlds_do_not_invent_human_population():
    for era in ("primordial-earth", "early-life"):
        p = plan_population(era, "pc-windows", "colony")
        assert p.local_limit == 1
        assert p.regional_limit == 0
        assert p.district_limit == 0
        assert p.visual_proxy_limit == 0


def test_gaming_profiles_are_conservative_even_on_high_end_hardware():
    p = plan_population("interstellar", "pc-windows", "exploration",
                        pc_generation="2020s-highend")
    assert p.local_limit <= 21
    assert p.regional_limit < 100
    assert p.visual_proxy_limit <= 10
    small = plan_population("interstellar", "game-boy", "platform")
    assert small.local_limit <= 3
    assert small.visual_proxy_limit == 0


def test_profile_is_real_instantiated_world_census_not_cosmetic_label():
    p = plan_population("interstellar", "playstation-5", "colony")
    s = game(hardware="playstation-5")
    assert s.population.profile == p
    assert len(s.society.inhabitants) == p.starting_locals
    assert len(s.cognition.minds) == p.starting_locals
    assert len(s.population.districts) == p.district_limit
    assert sum(d.population for d in s.population.districts) == p.regional_limit
    assert s.population.profile.local_limit <= 24
    assert validate_product(s)
    assert product_restore(product_save(s)) == s


def test_fixed_console_ignores_pc_generation_and_rejects_unavailable_hardware():
    with pytest.raises(FoundationError):
        plan_population("interstellar", "playstation-1", "colony",
                        pc_generation="2020s-highend")
    with pytest.raises(FoundationError):
        plan_population("interstellar", "pc-dos", "colony",
                        pc_generation="2020s-highend")
    with pytest.raises(FoundationError):
        plan_population("interstellar", "imaginary-console", "colony")
    with pytest.raises(FoundationError):
        plan_population("interstellar", "nes", "not-a-genre")
    with pytest.raises(FoundationError):
        plan_population("invented-era", "nes", "colony")


def test_real_era_local_cap_is_validated_not_bypassed_through_manual_count():
    p = plan_population("interstellar", "game-boy", "colony")
    with pytest.raises(FoundationError):
        game(hardware="game-boy", count=p.local_limit + 1)
    s = game(hardware="game-boy", count=p.local_limit)
    assert len(s.society.inhabitants) == p.local_limit
    assert validate_product(s)


def test_performance_mode_does_not_override_genre_cap_or_spawn_extra_fictional_npcs():
    state = game(hardware="nes", genre="racing", preset="unrestricted")
    cap = state.population.profile
    assert len(state.society.inhabitants) == cap.starting_locals
    scheduled = select_active_brains(
        state.population, state.society, state.terrain,
        state.cognition, preset="unrestricted")
    assert len(scheduled) <= cap.brain_limit
    assert len(scheduled) <= cap.local_limit
    state, receipt = step_product(state, ProductAction("causal", "end_turn"))
    assert len(state.society.inhabitants) == cap.starting_locals
    assert len(state.population.districts) == cap.district_limit


def test_ambient_crowd_budget_is_absolute_even_when_client_demands_more_sprites():
    s = game(hardware="playstation-2", genre="colony", preset="vivid")
    cap = s.population.profile
    visible = ambient_impressions(s.population, s.terrain, radius=20,
                                  max_visible=64)
    assert len(visible) <= cap.visual_proxy_limit
    assert all(x["is_simplified_visual_proxy"] and
               not x["has_individual_cognition"] for x in visible)
    early = game(hardware="nes", genre="platform")
    assert ambient_impressions(early.population, early.terrain,
                               radius=20, max_visible=64) == ()


def test_population_profile_cannot_be_forged_to_claim_larger_native_target():
    s = game(hardware="snes", genre="colony")
    bad = replace(s.population.profile, local_limit=24)
    forged = replace(s.population, profile=bad)
    with pytest.raises(FoundationError):
        validate_population(forged, s.society, s.terrain)
    saved = population_save(s.population)
    assert population_restore(saved, s.society, s.terrain) == s.population
    saved["payload"]["profile"]["regional_limit"] = 16384
    with pytest.raises(FoundationError):
        population_restore(saved, s.society, s.terrain)


def test_preexisting_high_density_v3_saves_are_accepted_only_as_legacy_records():
    s = game(hardware="playstation-5", genre="colony")
    # The previous release really did use a much higher simulated regional
    # census; upgrading must NOT destroy the user's saved world.
    legacy = create_era_population(
        s.terrain, s.society, s.population.era, profile=None,
        fidelity=s.population.fidelity)
    assert legacy.profile is None
    assert sum(d.population for d in legacy.districts) == 16384
    older = replace(s, population=legacy)
    assert product_restore(product_save(older)) == older
    envelope = json.loads(product_save(older))
    raw = envelope["payload"]["population"]["payload"]
    raw.pop("profile")
    from skeleton.game.generation.original_world_npc_era_population import _hash as phash
    from skeleton.game.generation.original_world_product_session import _hash as shash
    envelope["payload"]["population"]["checksum"] = phash(raw)
    envelope["checksum"] = shash(envelope["payload"])
    imported = product_restore(json.dumps(envelope))
    assert imported.population.profile is None
    assert len(imported.population.districts) > len(s.population.districts)


def test_cli_accepts_every_console_homebrew_pc_class_and_reports_real_not_ideal_cap(
        capsys, tmp_path):
    assert main([
        "--base", "0", "--form", "colony",
        "--architecture", "lattice", "--system", "trophic",
        "--arc", "sandbox", "--era", "interstellar",
        "--hardware-target", "nes", "--npc-fidelity", "unrestricted",
        "--population-report",
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    reported = summary["product"]["regional_population"]
    assert reported["detailed_limit"] <= 3
    assert reported["regional_aggregated_residents"] <= 2
    assert reported["full_local_brain_budget_per_turn"] <= 3
    assert reported["platform_genre_profile"]["platform"] == "nes"
    assert not reported["legacy_high_density"]
    save = tmp_path / "pc_colony.json"
    assert main([
        "--base", "0", "--form", "colony", "--architecture", "lattice",
        "--system", "trophic", "--arc", "sandbox",
        "--era", "interstellar", "--hardware-target", "pc-windows",
        "--pc-generation", "2020s-highend", "--population-report",
        "--save", str(save),
    ]) == 0
    high = json.loads(capsys.readouterr().out)
    assert high["product"]["regional_population"]["detailed_limit"] == 24
    assert main(["--load", str(save), "--population-report"]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["product"]["regional_population"]["platform_genre_profile"][
        "pc_generation"] == "2020s-highend"
    assert main(["--inventory"]) == 0
    inv = json.loads(capsys.readouterr().out)
    assert len(inv["realistic_npc_platform_profiles"]) == 41
