"""Evidence-focused tests for the original 81-domain game atlas."""
from __future__ import annotations

from collections import Counter
from math import comb

import pytest

from skeleton.game.generation.original_mechanic_catalog import MECHANICS, get_mechanic
from skeleton.game.generation.original_world_catalog import WORLDS, get_world
from skeleton.game.generation.original_world_compiler import (
    ATLAS_VERSION, DOMAINS, FOREIGN_DOMAINS, MECHANICS_BY_DOMAIN,
    MECHANICS_PER_WORLD, OriginalAtlasError, TOTAL_VARIANTS,
    VARIANTS_PER_WORLD, WORLD_IDS, blueprint_at, blueprint_for_world,
    blueprint_from_seed,
)
from skeleton.game.generation.world_experience_manifest import (
    experience_at, experience_from_seed, project_experience,
)
from skeleton.game.generation.world_styling import (
    CHRONOLOGIES, ERAS, HARDWARE_TARGETS, SIMULATION_REALISM, THEMES,
    THEOLOGIES, TONES, VISUAL_STYLES, WorldStyling,
)


def test_authored_world_inventory_is_unique_and_domain_complete() -> None:
    assert len(WORLDS) == 1296
    assert len(DOMAINS) == 81
    assert all(len([w for w in WORLDS.values() if w.domain == d]) == 16
               for d in DOMAINS)
    assert len({w.title.casefold() for w in WORLDS.values()}) == 1296
    assert len({w.invariant.casefold() for w in WORLDS.values()}) == 1296
    assert all(w.player_lever and w.invariant and w.ending_policy
               for w in WORLDS.values())


def test_mechanics_are_not_confused_with_unverified_world_levers() -> None:
    assert len(MECHANICS) == 1944
    assert len(DOMAINS) == len(MECHANICS_BY_DOMAIN)
    assert all(len(MECHANICS_BY_DOMAIN[d]) == 24 for d in DOMAINS)
    independent = [m for m in MECHANICS.values() if m.cost_specified]
    world_levers = [m for m in MECHANICS.values() if not m.cost_specified]
    assert len(independent) == 712
    assert len(world_levers) == 1232
    assert all(m.design_origin == "standalone" for m in independent)
    assert all(m.design_origin == "world-lever" for m in world_levers)
    assert all(m.trigger and m.state_change and m.drawback
               for m in MECHANICS.values())
    assert len({m.mechanic_id for m in MECHANICS.values()}) == 1944
    assert len({m.title.casefold() for m in independent}) == len(independent)


def test_exact_ranked_recipe_capacity_is_combinatorial_not_cosmetic() -> None:
    assert VARIANTS_PER_WORLD == comb(24, 2) * comb(80, 10) * 24**10
    assert TOTAL_VARIANTS == 1296 * VARIANTS_PER_WORLD
    assert TOTAL_VARIANTS == 37_341_018_089_543_468_949_354_074_603_520
    assert TOTAL_VARIANTS >= 10**30
    assert ATLAS_VERSION == "original-world-atlas.v2"


@pytest.mark.parametrize("index", [
    0, 1, 11, 12, 23, 24, 275, 276, 24**10 - 1, 24**10,
    VARIANTS_PER_WORLD - 1, VARIANTS_PER_WORLD,
    4 * VARIANTS_PER_WORLD + 1, TOTAL_VARIANTS // 2,
    TOTAL_VARIANTS - 1,
])
def test_blueprint_exact_replay_and_invariants(index: int) -> None:
    bp = blueprint_at(index)
    assert bp.as_dict() == blueprint_at(index).as_dict()
    assert bp.variant_index == index
    assert bp.as_dict()["variant_index"] == str(index)
    assert bp.atlas_version == ATLAS_VERSION
    assert len(bp.mechanics) == MECHANICS_PER_WORLD == 12
    assert len({m.mechanic_id for m in bp.mechanics}) == 12
    assert bp.domain_count == 1 + FOREIGN_DOMAINS == 11
    assert sum(m.domain == bp.world.domain for m in bp.mechanics) == 2
    assert bp.unresolved_lever_count + bp.specified_mechanic_count == 12
    assert bp.ending_policy == bp.world.ending_policy
    assert bp.realization_status == "design-only"
    assert len(bp.recipe_id) == 64
    assert len(bp.bridges) == comb(11, 2)
    selected_ids = {m.mechanic_id for m in bp.mechanics}
    for bridge in bp.bridges:
        assert bridge.origin in {"authored", "inferred"}
        assert bridge.from_mechanic in selected_ids
        assert bridge.to_mechanic in selected_ids
        assert bridge.consequence
    assert bp.authored_bridge_count == sum(
        bridge.origin == "authored" for bridge in bp.bridges
    )
    assert blueprint_for_world(bp.world.world_id, index % VARIANTS_PER_WORLD).recipe_id == bp.recipe_id


def test_sampled_recipes_differ_by_causal_mechanic_identity() -> None:
    indices = {
        (n * 104729) % TOTAL_VARIANTS for n in range(256)
    } | {
        (n * 11_111_111_111_111_111) % TOTAL_VARIANTS for n in range(256)
    } | {
        n * VARIANTS_PER_WORLD for n in range(len(WORLD_IDS))
    }
    signature = [
        (bp.world.world_id, tuple(m.mechanic_id for m in bp.mechanics))
        for index in indices for bp in (blueprint_at(index),)
    ]
    assert len(set(signature)) == len(indices)


def test_all_worlds_keep_intended_ending_policies() -> None:
    policy_counts = Counter(world.ending_policy for world in WORLDS.values())
    assert all(policy_counts[policy] for policy in (
        "closed", "open", "postgame", "persistent", "unwinnable",
        "branched", "looping",
    ))
    for world in WORLDS.values():
        bp = blueprint_for_world(world.world_id, 0)
        assert bp.world == world
        assert bp.ending_policy == world.ending_policy


def test_style_axis_inventory_and_orthogonality() -> None:
    assert len(ERAS) == 40
    assert len(CHRONOLOGIES) == 32
    assert len(THEOLOGIES) == 24
    assert len(THEMES) == 81
    assert len(VISUAL_STYLES) == 32
    assert len(TONES) == 24
    assert len(SIMULATION_REALISM) == 12
    assert len(HARDWARE_TARGETS) == 41
    cozy = WorldStyling(
        era="paleolithic", chronology="remote-past", theology="animist-invented",
        themes=("comfort", "mystery"), visual_style="monochrome-pixel",
        tone="ultra-snuggly", simulation_realism="simulation-heavy",
        comfort=100, realism=88, hardware_target="game-boy",
    )
    intense = WorldStyling(
        era="deep-future", chronology="fractured-time",
        theology="cosmic-mythic", themes=("cosmic-horror", "discovery"),
        visual_style="photorealistic-target", tone="nightmarish",
        simulation_realism="hyperrealism-target",
        comfort=2, realism=100, hardware_target="pc-windows",
    )
    assert cozy.comfort == 100 and cozy.realism == 88
    assert intense.comfort == 2 and intense.realism == 100
    assert cozy.as_dict()["themes"] == ["comfort", "mystery"]


def test_repeated_recipe_styles_have_distinct_presentation_ids() -> None:
    core = blueprint_at(123456789)
    cozy = project_experience(core, WorldStyling(
        tone="ultra-snuggly", comfort=100, realism=96,
        simulation_realism="environmental-sim",
    ))
    horror = project_experience(core, WorldStyling(
        tone="nightmarish", comfort=5, realism=96,
        simulation_realism="environmental-sim",
    ))
    assert cozy.blueprint.recipe_id == horror.blueprint.recipe_id
    assert cozy.experience_id != horror.experience_id
    assert cozy.continuity_contract
    assert cozy.platform_readiness == "adapter-not-verified"
    assert cozy.realization_status == "design-only"
    assert experience_at(core.variant_index).experience_id == project_experience(core).experience_id
    assert experience_from_seed("replay").as_dict() == experience_from_seed("replay").as_dict()


def test_experience_flags_incompatible_visual_and_hardware_demands() -> None:
    bp = blueprint_at(0)
    manifest = project_experience(bp, WorldStyling(
        era="early-life", chronology="before-time",
        theology="atheist-world", themes=("divinity", "wonder"),
        visual_style="photorealistic-target", tone="nightmarish",
        simulation_realism="hyperrealism-target",
        comfort=100, realism=100, hardware_target="game-boy",
    ))
    warnings = " ".join(manifest.compatibility_findings)
    assert "retro" in warnings
    assert "comfort" in warnings
    assert "divine theme" in warnings
    assert manifest.realization_status == "design-only"


@pytest.mark.parametrize("index", [-1, TOTAL_VARIANTS, True, False, 0.1, "1", None])
def test_invalid_global_indices_rejected(index: object) -> None:
    with pytest.raises(OriginalAtlasError):
        blueprint_at(index)


@pytest.mark.parametrize("index", [-1, VARIANTS_PER_WORLD, True, "0", None])
def test_invalid_local_indices_rejected(index: object) -> None:
    with pytest.raises(OriginalAtlasError):
        blueprint_for_world(WORLD_IDS[0], index)


@pytest.mark.parametrize("bad", ["", None, 42, "x" * 4097])
def test_invalid_seeds_rejected(bad: object) -> None:
    with pytest.raises(OriginalAtlasError):
        blueprint_from_seed(bad)


@pytest.mark.parametrize("params", [
    {"era": "missing"}, {"chronology": "future-ish"},
    {"theology": "unverified-real-religion"},
    {"visual_style": "unknown-renderer"}, {"tone": "invalid"},
    {"simulation_realism": "magical-correctness"},
    {"hardware_target": "secret-console"},
    {"themes": ()}, {"themes": ("mystery", "mystery")},
    {"themes": ("missing",)}, {"themes": ["mystery"]},
    {"comfort": -1}, {"comfort": 101}, {"comfort": True},
    {"realism": 1.5}, {"realism": False},
])
def test_invalid_styling_rejected(params: dict) -> None:
    with pytest.raises((ValueError, TypeError)):
        WorldStyling(**params)


def test_lookup_and_serialized_view_are_safe() -> None:
    a = blueprint_from_seed("dragon-original-2026")
    assert a.recipe_id == blueprint_from_seed("dragon-original-2026").recipe_id
    assert get_world(a.world.world_id) == a.world
    assert get_mechanic(a.mechanics[0].mechanic_id) == a.mechanics[0]
    assert blueprint_from_seed("another-prototype").recipe_id != a.recipe_id
    with pytest.raises(ValueError):
        get_world("missing-01")
    with pytest.raises(ValueError):
        get_mechanic("missing-01")
    with pytest.raises(OriginalAtlasError):
        blueprint_for_world("missing-01", 0)
    projection = a.as_dict()
    projection["world"]["invariant"] = "mutated"
    projection["mechanics"][0]["state_change"] = "mutated"
    projection["bridges"][0]["consequence"] = "mutated"
    assert blueprint_at(a.variant_index).world.invariant != "mutated"
    assert blueprint_at(a.variant_index).mechanics[0].state_change != "mutated"
    assert blueprint_at(a.variant_index).bridges[0].consequence != "mutated"
