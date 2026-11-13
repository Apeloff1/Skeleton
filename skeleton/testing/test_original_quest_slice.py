"""Integration tests for archived mechanics → synthesis → objective runtime."""
from __future__ import annotations

from copy import deepcopy
import pytest

from skeleton.ai.game_builder.constraint_quest_synthesis import ContentPolicy, WorldModel
from skeleton.ai.game_builder.genre_template_composition import PackRegistry
from skeleton.ai.game_builder.original_quest_slice import (
    SliceBuildError, compose_verified_quest_slice, verify_original_slice,
)

PACKS = [
    {"id": "movement", "provides": ["movement"]},
    {"id": "quest", "provides": ["quests"], "requires": ["movement"]},
    {"id": "combat", "provides": ["combat"], "requires": ["movement"]},
]
WORLD = WorldModel(
    start="village",
    edges={"village": ("forest",), "forest": ("village", "cave"), "cave": ()},
    npcs={"blacksmith": "village", "ranger": "forest"},
)
POLICY = ContentPolicy(max_reward_per_step=20, max_total_reward=80)


def build():
    registry = PackRegistry(PACKS)
    return registry, compose_verified_quest_slice(
        registry, ["quest", "movement", "combat"],
        slice_id="original-world", world=WORLD, policy=POLICY,
        seed=7, quest_length=3,
    )


def test_independent_mechanics_and_quest_engines_prove_one_slice():
    registry, slice_doc = build()
    assert slice_doc["mechanics"]["capabilities"]["quests"] == "quest"
    assert len(slice_doc["world_quest"]["quest"]["steps"]) == 3
    assert slice_doc["proof"]["status"] == "completed"
    assert verify_original_slice(slice_doc, registry)
    assert build()[1] == slice_doc


def test_tampering_breaks_receipt_validation():
    registry, original = build()
    modified = deepcopy(original)
    modified["quest_definition"]["objectives"][0]["target"] = 9999
    assert not verify_original_slice(modified, registry)
    modified = deepcopy(original)
    modified["mechanics"]["packs"][0]["digest"] = "bad"
    assert not verify_original_slice(modified, registry)


def test_quest_pack_dependency_and_missing_quest_pack_fail_closed():
    registry = PackRegistry(PACKS)
    with pytest.raises(SliceBuildError):
        compose_verified_quest_slice(
            registry, ["combat"], slice_id="a", world=WORLD, policy=POLICY, seed=1,
        )
    with pytest.raises(SliceBuildError):
        compose_verified_quest_slice(
            registry, ["movement"], slice_id="a", world=WORLD, policy=POLICY, seed=1,
        )


def test_impossible_reward_policy_cannot_emit_a_passing_slice():
    registry = PackRegistry(PACKS)
    with pytest.raises((SliceBuildError, ValueError)):
        compose_verified_quest_slice(
            registry, ["movement", "quest"], slice_id="a", world=WORLD,
            policy=ContentPolicy(max_reward_per_step=100, max_total_reward=0),
            seed=2, quest_length=5,
        )


@pytest.mark.parametrize("slice_id", ("", "a" * 129, None))
def test_invalid_slice_names_rejected(slice_id):
    with pytest.raises(SliceBuildError):
        compose_verified_quest_slice(
            PackRegistry(PACKS), ["movement", "quest"], slice_id=slice_id,
            world=WORLD, policy=POLICY, seed=1,
        )
