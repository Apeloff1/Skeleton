"""Evidence-bearing NPC oral histories and genuinely social knowledge transfer."""
from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_npc_cognition_v2 import (
    Memory, make_intelligence, smart_npc_tick, cognition_save,
    cognition_restore, cognition_report, interview_citizen,
)
from skeleton.game.generation.original_world_product_terrain import create_terrain
from skeleton.game.generation.original_world_product_agents import create_society
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, step_product, product_save, product_restore,
    validate_product,
)
from skeleton.game.generation.original_world_product_cli import parse_command


def product(n=2):
    index = living_for(0, "puzzle", "lattice", "trophic", "sandbox").index
    return create_product(index, inhabitants=n)


def test_situated_citizen_witness_is_promoted_once_to_real_game_evidence():
    state = product(1)
    person = state.society.inhabitants[0]
    witness = Memory(0, "food", (person.x, person.y), 3, 100, person.id)
    first = state.cognition.minds[0]
    cognition = replace(state.cognition, minds=(
        replace(first, memories=(witness,)),
    ))
    state = replace(state, cognition=cognition)
    initial = state.living.spatial.game.causal.evidence
    state, proof = step_product(state, ProductAction("npc", "interview",
                                                     target=0, option="food"))
    assert state.living.spatial.game.causal.evidence == initial + 1
    assert len(state.cognition.testimonies) == 1
    assert state.cognition.testimonies[0].subject == "food"
    assert state.cognition.testimonies[0].confidence == 100
    assert state.living.spatial.game.causal.action_points == 3
    assert "first-hand evidence" in " ".join(proof.changes)
    with pytest.raises(FoundationError):
        step_product(state, ProductAction("npc", "interview",
                                          target=0, option="food"))
    assert product_restore(product_save(state)) == state


def test_no_fabricated_knowledge_or_old_unwitnessed_rumors_are_promoted():
    state = product(1)
    with pytest.raises(FoundationError):
        step_product(state, ProductAction("npc", "interview", target=0))
    earlier = Memory(0, "wood", (0, 0), 4, 40, 0)
    state = replace(state, cognition=replace(
        state.cognition, minds=(replace(state.cognition.minds[0],
                                        memories=(earlier,)),),
    ))
    with pytest.raises(FoundationError):
        step_product(state, ProductAction("npc", "interview", target=0))
    assert state.living.spatial.game.causal.evidence == 2


def test_socially_transmitted_memory_cannot_masquerade_as_direct_eyewitness():
    world = create_terrain("2" * 64)
    residents = create_society(world, 2)
    citizens = tuple(replace(p, x=0, y=0,
                             profession="guardian") for p in residents.inhabitants)
    residents = replace(residents, inhabitants=citizens)
    minds = make_intelligence(world, residents)
    eyewitness = Memory(0, "stone", (4, 0), 5, 100, 0)
    minds = replace(minds, minds=(
        replace(minds.minds[0], loneliness=20, memories=(eyewitness,)),
        replace(minds.minds[1], loneliness=20),
    ))
    for _ in range(2):
        world, residents, minds, physical, decisions = smart_npc_tick(
            world, residents, minds)
    assert len(minds.bonds) == 1
    assert minds.bonds[0].trust >= 2
    shared = [
        r for r in minds.minds[1].memories
        if r.subject == "stone" and r.position == (4, 0)
    ]
    assert shared, "a real nearby social bond must transfer witnessed geographical knowledge"
    assert shared[-1].confidence <= 80
    assert shared[-1].witness == 0
    assert shared[-1].turn == 0
    assert cognition_report(minds, residents, world)[
        "socially_learned_material_observations"] >= 1
    # A citizen may genuinely have other personal stone observations.
    # Isolate just the third-party report to prove that its original witness
    # cannot masquerade as a new eyewitness after social retelling.
    shared_only = replace(minds, minds=(
        minds.minds[0],
        replace(minds.minds[1], memories=tuple(shared)),
    ))
    with pytest.raises(FoundationError):
        interview_citizen(shared_only, residents, world,
                          citizen=1, subject="stone")
    assert cognition_restore(cognition_save(minds), residents, world) == minds


def test_citizen_testimony_requires_proximity_and_limited_original_evidence_slots():
    state = product(1)
    witness = Memory(0, "water", (0, 0), 2, 100, 0)
    state = replace(state, cognition=replace(state.cognition, minds=(
        replace(state.cognition.minds[0], memories=(witness,)),
    )))
    state = replace(state, terrain=replace(state.terrain, position=(9, 0)))
    with pytest.raises(FoundationError):
        step_product(state, ProductAction("npc", "interview", target=0))
    assert parse_command("npc interview 0 water", (0, 0)) == ProductAction(
        "npc", "interview", target=0, option="water",
    )


def test_citizen_mental_state_report_is_a_transparent_causal_observation():
    state = product(3)
    before = asdict(state)
    report = cognition_report(state.cognition, state.society, state.terrain)
    assert report["socially_learned_material_observations"] == 0
    assert report["first_hand_testimonies"] == []
    assert report["report_not_an_llm"]
    assert before == asdict(state)


def test_goal_weights_learn_from_verified_delivery_not_arbitrary_idle_loops():
    from skeleton.game.generation.original_world_npc_cognition_v2 import GOAL_ORDER
    s = product(1)
    s, _ = step_product(s, ProductAction(
        "npc", "commission", target=0, option="food"))
    s, _ = step_product(s, ProductAction("causal", "end_turn"))
    learned = dict(zip(GOAL_ORDER, s.cognition.minds[0].learned))
    assert learned["work"] >= 2
    s, _ = step_product(s, ProductAction("causal", "end_turn"))
    learned = dict(zip(GOAL_ORDER, s.cognition.minds[0].learned))
    assert learned["deliver"] >= 2
    assert s.cognition.orders[0].status == "fulfilled"
    assert product_restore(product_save(s)) == s


def test_failed_construction_feedback_discourages_repeated_unfunded_plans():
    from skeleton.game.generation.original_world_npc_cognition_v2 import GOAL_ORDER
    s = product(1)
    engineer = replace(s.society.inhabitants[0], profession="builder")
    s = replace(s,
                society=replace(s.society, inhabitants=(engineer,)),
                terrain=replace(s.terrain, lumber=0, masonry=0))
    s, _ = step_product(s, ProductAction("causal", "end_turn"))
    result = dict(zip(GOAL_ORDER, s.cognition.minds[0].learned))
    assert result["construct"] == -2
    assert not s.terrain.edits
    assert s.terrain.lumber == s.terrain.masonry == 0


def test_invalid_learned_utility_cannot_be_loaded_even_with_adjusted_memory_checks():
    from skeleton.game.generation.original_world_npc_cognition_v2 import (
        validate_intelligence,
    )
    s = product(1)
    fake_mind = replace(s.cognition.minds[0], learned=(999,) * 10)
    fake_cognition = replace(s.cognition, minds=(fake_mind,))
    with pytest.raises(FoundationError):
        validate_intelligence(fake_cognition, s.society, s.terrain)
