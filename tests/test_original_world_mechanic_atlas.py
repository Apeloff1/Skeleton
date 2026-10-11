"""Regression tests for exact-index original world design compilation."""
from __future__ import annotations

from collections import Counter

import pytest

from skeleton.game.generation.original_mechanic_catalog import MECHANICS, get_mechanic
from skeleton.game.generation.original_world_catalog import WORLDS, get_world
from skeleton.game.generation.original_world_compiler import (
    ATLAS_VERSION, DOMAINS, FOREIGN_DOMAINS, MECHANICS_BY_DOMAIN,
    MECHANICS_PER_WORLD, OriginalAtlasError, TOTAL_VARIANTS,
    VARIANTS_PER_WORLD, WORLD_IDS, blueprint_at, blueprint_for_world,
    blueprint_from_seed,
)


def test_catalog_is_curated_and_complete() -> None:
    assert len(WORLDS) == 128
    assert len(MECHANICS) == 192
    assert len(DOMAINS) == 16
    assert {world.domain for world in WORLDS.values()} == set(DOMAINS)
    assert {mechanic.domain for mechanic in MECHANICS.values()} == set(DOMAINS)
    assert len({world.invariant.casefold() for world in WORLDS.values()}) == 128
    assert len({mechanic.title.casefold() for mechanic in MECHANICS.values()}) == 192
    assert all(len(MECHANICS_BY_DOMAIN[domain]) == 12 for domain in DOMAINS)
    assert all(len({world.world_id for world in WORLDS.values()
                    if world.domain == domain}) == 8 for domain in DOMAINS)
    assert all(world.player_lever and world.invariant
               for world in WORLDS.values())
    assert all(m.trigger and m.state_change and m.drawback
               for m in MECHANICS.values())


def test_actual_recipe_capacity_exceeds_quintillion() -> None:
    assert TOTAL_VARIANTS == 1_570_802_912_571_949_056
    assert TOTAL_VARIANTS == 128 * VARIANTS_PER_WORLD
    assert TOTAL_VARIANTS >= 10**18


@pytest.mark.parametrize("index", [
    0, 1, 11, 12, 65, 66, 12**10, VARIANTS_PER_WORLD - 1,
    VARIANTS_PER_WORLD, 4 * VARIANTS_PER_WORLD + 1,
    TOTAL_VARIANTS // 2, TOTAL_VARIANTS - 1,
])
def test_blueprint_is_exact_and_causally_specific(index: int) -> None:
    first = blueprint_at(index)
    second = blueprint_at(index)
    assert first.as_dict() == second.as_dict()
    assert first.variant_index == index
    assert first.atlas_version == ATLAS_VERSION
    assert len(first.mechanics) == MECHANICS_PER_WORLD == 12
    assert len({mechanic.mechanic_id for mechanic in first.mechanics}) == 12
    assert first.domain_count == 1 + FOREIGN_DOMAINS == 11
    assert sum(m.domain == first.world.domain for m in first.mechanics) == 2
    assert first.ending_policy == first.world.ending_policy
    assert first.realization_status == "design-only"
    assert len(first.recipe_id) == 64
    mechanic_ids = {mechanic.mechanic_id for mechanic in first.mechanics}
    for bridge in first.bridges:
        assert bridge.from_mechanic in mechanic_ids
        assert bridge.to_mechanic in mechanic_ids
        assert bridge.from_mechanic != bridge.to_mechanic
        assert bridge.consequence
    assert blueprint_for_world(
        first.world.world_id, index % VARIANTS_PER_WORLD
    ).recipe_id == first.recipe_id


def test_unranking_is_unique_across_decisive_boundaries() -> None:
    sample = [0, 1, 2, 11, 12, 13, 143, 144, 145]
    sample += [12**10 * n for n in range(32)]
    sample += [VARIANTS_PER_WORLD * n for n in range(len(WORLD_IDS))]
    sample += [TOTAL_VARIANTS - 1 - n for n in range(32)]
    signatures = [
        (blueprint_at(i).world.world_id,
         tuple(m.mechanic_id for m in blueprint_at(i).mechanics))
        for i in sample
    ]
    assert len(set(signatures)) == len(set(sample))


def test_random_sample_does_not_collapse_to_cosmetic_reskins() -> None:
    # Exercise unranking across multiple positions without scanning the
    # combinatorial space or claiming that every recipe is a playable game.
    indices = {
        (n * 104_729) % TOTAL_VARIANTS
        for n in range(512)
    } | {
        (n * 11_111_111_111_111_111) % TOTAL_VARIANTS
        for n in range(512)
    }
    signatures = [
        (bp.world.world_id, tuple(m.mechanic_id for m in bp.mechanics))
        for index in indices for bp in (blueprint_at(index),)
    ]
    assert len(set(signatures)) == len(indices)


def test_family_and_continuity_coverage() -> None:
    counts = Counter(world.ending_policy for world in WORLDS.values())
    assert all(counts[k] for k in (
        "closed", "open", "postgame", "persistent", "unwinnable",
        "branched", "looping",
    ))
    for world in WORLDS.values():
        candidate = blueprint_for_world(world.world_id, 0)
        assert candidate.ending_policy == world.ending_policy


@pytest.mark.parametrize("index", [-1, TOTAL_VARIANTS, True, False, 0.1, "1", None])
def test_invalid_global_indices_are_rejected(index: object) -> None:
    with pytest.raises(OriginalAtlasError):
        blueprint_at(index)


@pytest.mark.parametrize("index", [-1, VARIANTS_PER_WORLD, True, "0", None])
def test_invalid_local_indices_are_rejected(index: object) -> None:
    with pytest.raises(OriginalAtlasError):
        blueprint_for_world(WORLD_IDS[0], index)


@pytest.mark.parametrize("bad", ["", None, 42, "x" * 4097])
def test_invalid_seeds_are_rejected(bad: object) -> None:
    with pytest.raises(OriginalAtlasError):
        blueprint_from_seed(bad)


def test_seed_replay_and_error_contracts() -> None:
    a = blueprint_from_seed("dragon-original-2026")
    b = blueprint_from_seed("dragon-original-2026")
    assert a.recipe_id == b.recipe_id
    assert a.as_dict() == b.as_dict()
    assert get_world(a.world.world_id) == a.world
    assert get_mechanic(a.mechanics[0].mechanic_id) == a.mechanics[0]
    assert blueprint_from_seed("another-prototype").recipe_id != a.recipe_id
    with pytest.raises(ValueError):
        get_world("missing-01")
    with pytest.raises(ValueError):
        get_mechanic("missing-01")
    with pytest.raises(OriginalAtlasError):
        blueprint_for_world("missing-01", 0)


def test_serialized_view_does_not_mutate_registry() -> None:
    bp = blueprint_at(1)
    data = bp.as_dict()
    data["world"]["invariant"] = "overwritten"
    data["mechanics"][0]["state_change"] = "overwritten"
    if data["bridges"]:
        data["bridges"][0]["consequence"] = "overwritten"
    reloaded = blueprint_at(1)
    assert reloaded.world.invariant != "overwritten"
    assert reloaded.mechanics[0].state_change != "overwritten"
    assert all(bridge.consequence != "overwritten"
               for bridge in reloaded.bridges)
