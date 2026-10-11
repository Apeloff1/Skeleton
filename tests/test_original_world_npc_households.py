"""Intergenerational physically grounded NPC families with funded childcare."""
from __future__ import annotations

from dataclasses import replace
import json
import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_npc_households import (
    GESTATION, CHILDCARE_TURNS, Household, HouseholdState,
    validate_households, household_save, household_restore, household_report,
)
from skeleton.game.generation.original_world_npc_cognition_v2 import (
    _bond_change, npc_profile,
)
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, step_product, product_save,
    product_restore, validate_product,
)
from skeleton.game.generation.original_world_product_cli import parse_command


def product(n=2):
    law = living_for(0, "puzzle", "lattice", "trophic", "sandbox")
    return create_product(law.index, inhabitants=n)


def move_in(state):
    residents = tuple(replace(p, x=0, y=0, health=20, hunger=0, energy=4)
                      for p in state.society.inhabitants)
    state = replace(state, society=replace(state.society, inhabitants=residents))
    cognition = _bond_change(
        state.cognition, 0, 1, affinity=3, trust=3, aid=2,
    )
    state = replace(state, cognition=cognition)
    state, _ = step_product(state, ProductAction(
        "terrain", "build_hearth", x=0, y=0,
    ))
    return state


def propose(state):
    return step_product(state, ProductAction(
        "npc", "household", target=0, option="1",
    ))[0]


def turn(state):
    return step_product(state, ProductAction("causal", "end_turn"))[0]


def test_family_creation_requires_actual_trust_real_house_both_caregivers_and_escrow():
    base = product()
    with pytest.raises(FoundationError):
        propose(base)
    equipped = move_in(base)
    prior = (equipped.terrain.provisions, equipped.terrain.freshwater,
             equipped.living.spatial.game.causal.trust)
    funded = propose(equipped)
    assert (funded.terrain.provisions, funded.terrain.freshwater) == (
        prior[0] - 3, prior[1] - 2
    )
    assert funded.living.spatial.game.causal.trust == prior[2] - 1
    assert funded.cognition.households.families[0].status == "awaiting"
    assert len(funded.society.inhabitants) == 2
    assert len(funded.cognition.minds) == 2


def test_new_dependent_is_born_only_after_three_real_days():
    state = propose(move_in(product()))
    for day in range(1, GESTATION + 1):
        state = turn(state)
        if day < GESTATION:
            assert len(state.society.inhabitants) == 2
        else:
            assert len(state.society.inhabitants) == 3
            assert len(state.cognition.minds) == 3
            assert state.society.inhabitants[2].id == 2
            assert state.cognition.minds[2].person_id == 2
            assert state.cognition.households.ages == (24 + day, 24 + day, 0)
            assert state.cognition.households.completed == 1
            assert state.cognition.households.families[0].status == "established"
    assert product_restore(product_save(state)) == state
    assert validate_product(state)
    child = npc_profile(state.cognition, state.society, state.terrain, 2)
    assert child["age_in_world_turns"] == 0
    assert child["identity"] == 2
    assert child["individually_simulated_not_a_language_model"]


def test_protected_young_citizen_has_real_care_cost_and_cannot_harvest_immediately():
    state = propose(move_in(product()))
    for _ in range(3):
        state = turn(state)
    child = state.society.inhabitants[2]
    assert child.profession == "caretaker"
    day0_experience = child.experience
    state = turn(state)
    child = state.society.inhabitants[2]
    assert state.cognition.households.ages[2] == 1
    assert child.experience == day0_experience
    assert state.cognition.minds[2].goal == "recover"
    assert 0 <= child.health <= 20
    assert product_restore(product_save(state)) == state


def test_cancelled_household_returns_exact_reserved_resources_without_new_person():
    equipped = move_in(product())
    base_food, base_water = equipped.terrain.provisions, equipped.terrain.freshwater
    state = propose(equipped)
    state, _ = step_product(state, ProductAction(
        "npc", "cancel_household", target=0,
    ))
    assert state.terrain.provisions == base_food
    assert state.terrain.freshwater == base_water
    assert state.cognition.households.families[0].status == "cancelled"
    for _ in range(4):
        state = turn(state)
    assert len(state.society.inhabitants) == 2
    assert state.cognition.households.completed == 0
    with pytest.raises(FoundationError):
        step_product(state, ProductAction("npc", "cancel_household", target=0))


def test_two_caregivers_cannot_overfill_physical_settlement():
    state = move_in(product())
    state = propose(state)
    with pytest.raises(FoundationError):
        propose(state)
    assert len(state.cognition.households.families) == 1


def test_generated_child_biography_is_persistent_and_replay_deterministic():
    def journey():
        state = propose(move_in(product()))
        for _ in range(5):
            state = turn(state)
        return state
    a, b = journey(), journey()
    assert a == b
    assert product_save(a) == product_save(b)
    assert a.cognition.minds[2].curiosity >= 1
    assert a.cognition.minds[2].empathy >= 1
    assert len(a.cognition.bonds) >= 2
    assert household_report(a.cognition.households)[
        "actually_established_dependents"] == 1


def test_household_records_are_checksum_protected_and_cannot_forge_children():
    state = propose(move_in(product()))
    envelope = household_save(state.cognition.households)
    assert household_restore(envelope, state.society,
                             state.terrain) == state.cognition.households
    forged = replace(state.cognition.households, completed=1)
    with pytest.raises(FoundationError):
        validate_households(forged, state.society, state.terrain)
    envelope["payload"]["completed"] = 99
    with pytest.raises(FoundationError):
        household_restore(envelope, state.society, state.terrain)


def test_old_cognition_saves_without_family_extension_start_only_adult_ages():
    from skeleton.game.generation.original_world_npc_cognition_v2 import _hash
    state = product()
    saved = json.loads(product_save(state))
    cognition = saved["payload"]["cognition"]
    cognition["payload"].pop("households")
    cognition["checksum"] = _hash(cognition["payload"])
    from skeleton.game.generation.original_world_product_session import _hash as h
    saved["checksum"] = h(saved["payload"])
    recovered = product_restore(json.dumps(saved))
    assert recovered.cognition.households.ages == (24, 24)
    assert not recovered.cognition.households.families


def test_household_terminal_commands_have_real_scope():
    assert parse_command("npc household 0 1", (0, 0)) == ProductAction(
        "npc", "household", target=0, option="1",
    )
    assert parse_command("npc cancel_household 0", (0, 0)).target == 0
