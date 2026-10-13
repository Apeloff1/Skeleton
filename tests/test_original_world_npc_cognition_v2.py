"""NPC v2 cognition: identity, causal work, memory, care, trust, persistence.

Unlike simple profession bots, these tests require executable physical tasks,
real resource accounting and provenance across changing citizen needs.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_npc_cognition_v2 import (
    VERSION, Bond, Memory, Mind, Order,
    make_intelligence, validate_intelligence,
    smart_npc_tick, cognition_save, cognition_restore,
    cognition_report, commission, cancel_order, _bond_change,
)
from skeleton.game.generation.original_world_product_terrain import (
    create_terrain, cell_at,
)
from skeleton.game.generation.original_world_product_agents import (
    create_society, Person,
)
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, product_save, product_restore,
    step_product, validate_product, LEGACY_SCHEMA,
)
from skeleton.game.generation.original_world_product_cli import main, parse_command

DESIGN = "3" * 64


def sample(count=12):
    ground = create_terrain(DESIGN)
    bodies = create_society(ground, count)
    minds = make_intelligence(ground, bodies)
    return ground, bodies, minds


def product(*, inhabitants=12):
    index = living_for(0, "puzzle", "lattice", "trophic", "sandbox").index
    return create_product(index, inhabitants=inhabitants)


def act(s, layer, verb, *, target=-1, amount=1, option=""):
    return step_product(s, ProductAction(layer, verb, amount=amount,
                                         target=target, option=option))[0]


def test_all_citizens_have_individual_real_traits_and_distinct_persistent_minds():
    world, people, minds = sample()
    assert minds.world_id == world.design_id
    assert len(minds.minds) == len(people.inhabitants) == 12
    assert {m.person_id for m in minds.minds} == set(range(12))
    assert len({(m.temperament, m.curiosity, m.empathy,
                 m.discipline, m.prudence) for m in minds.minds}) >= 8
    assert all(1 <= m.empathy <= 10 for m in minds.minds)
    assert all(m.decisions == 0 and not m.memories for m in minds.minds)


def test_cognitive_ticks_replan_without_teleportation_or_free_energy():
    world, people, minds = sample()
    for day in range(8):
        previous = people
        world, people, minds, receipts, reasoning = smart_npc_tick(world, people, minds)
        validate_intelligence(minds, people, world)
        assert people.tick == minds.day == day + 1
        assert len(receipts) == len(reasoning) == 12
        for before, after, evidence in zip(previous.inhabitants,
                                           people.inhabitants, reasoning):
            assert abs(before.x-after.x) + abs(before.y-after.y) <= 1
            assert not cell_at(world, after.x, after.y).blocking
            assert evidence.person_id == before.id
            assert evidence.utility >= 0
            assert evidence.action
            assert 0 <= after.energy <= 20
            assert 0 <= after.health <= 20
            assert 0 <= after.hunger <= 20
            assert 1 <= len(minds.minds[before.id].memories) <= 16


def test_issued_npc_work_order_uses_actual_tile_and_finite_depot_delivery():
    state = product(inhabitants=1)
    origin = cell_at(state.terrain, 0, 0)
    before = state.terrain.provisions + origin.food
    state = act(state, "npc", "commission", target=0, option="food")
    assert len(state.cognition.orders) == 1
    assert state.cognition.orders[0].status == "open"
    assert state.living.spatial.game.causal.trust == 8
    state = act(state, "causal", "end_turn")
    assert state.society.inhabitants[0].cargo == 1
    assert cell_at(state.terrain, 0, 0).food == origin.food - 1
    state = act(state, "causal", "end_turn")
    assert state.cognition.orders[0].status == "fulfilled"
    assert state.cognition.orders[0].delivered == 1
    assert state.terrain.provisions == 6
    assert state.terrain.provisions + cell_at(state.terrain, 0, 0).food == before


def test_contract_cannot_double_spend_or_reuse_identical_order_id():
    state = product(inhabitants=1)
    state = act(state, "npc", "commission", target=0, option="food")
    with pytest.raises(FoundationError):
        act(state, "npc", "commission", target=0, option="food")
    state = act(state, "npc", "cancel", target=0)
    assert state.cognition.orders[0].status == "cancelled"
    with pytest.raises(FoundationError):
        act(state, "npc", "cancel", target=0)
    state = act(state, "npc", "commission", target=0, option="wood")
    assert [o.order_id for o in state.cognition.orders] == [0, 1]


def test_worker_can_reject_impossible_resource_and_invalid_worker_identity():
    s = product(inhabitants=1)
    for target, material in ((99, "food"), (0, "imaginary")):
        with pytest.raises(FoundationError):
            act(s, "npc", "commission", target=target, option=material)
    assert s.cognition.orders == ()
    assert s.living.spatial.game.causal.trust == 9


def test_player_gifts_are_recorded_in_people_and_individual_memories():
    s = product(inhabitants=1)
    before = s.terrain.provisions
    s = act(s, "studio", "gift", target=0)
    assert s.terrain.provisions == before - 1
    assert s.cognition.interventions == 1
    assert s.cognition.minds[0].memories[-1].subject == "friend"
    assert s.cognition.minds[0].memories[-1].confidence == 100
    assert s.society.inhabitants[0].relationships == 5
    assert s.cognition.minds[0].morale == 11


def test_thoughts_have_bounded_persistent_observations_with_authentic_coordinates():
    world, people, minds = sample(1)
    for _ in range(15):
        world, people, minds, _, _ = smart_npc_tick(world, people, minds)
    assert len(minds.minds[0].memories) <= 16
    for record in minds.minds[0].memories:
        assert record.turn <= minds.day
        assert record.position
        assert record.subject in ("food", "wood", "stone", "water")
        assert record.witness == 0


def test_cognition_saves_roundtrip_and_replay_remains_bytewise_identical():
    def run():
        s = product(inhabitants=4)
        s = act(s, "npc", "commission", target=0, option="food")
        for _ in range(5):
            s = act(s, "causal", "end_turn")
        assert product_restore(product_save(s)) == s
        return s
    a, b = run(), run()
    assert a == b
    assert cognition_save(a.cognition) == cognition_save(b.cognition)


def test_rejects_forged_future_memories_duplicate_relationships_and_cargo():
    ground, bodies, brain = sample(4)
    corrupt = replace(brain, minds=(replace(
        brain.minds[0],
        memories=(Memory(20, "wood", (0, 0), 900, 100, 0),)
    ), *brain.minds[1:]))
    with pytest.raises(FoundationError):
        validate_intelligence(corrupt, bodies, ground)
    malformed = replace(brain, bonds=(Bond(0, 1), Bond(0, 1)))
    with pytest.raises(FoundationError):
        validate_intelligence(malformed, bodies, ground)
    envelope = cognition_save(brain)
    envelope["payload"]["next_order"] = 10
    with pytest.raises(FoundationError):
        cognition_restore(envelope, bodies, ground)


def test_older_game_save_is_migrated_without_inventing_historical_memories():
    s = product(inhabitants=3)
    s = act(s, "causal", "end_turn")
    packaged = json.loads(product_save(s))
    packaged["payload"]["schema"] = LEGACY_SCHEMA
    packaged["payload"].pop("cognition")
    from skeleton.game.generation.original_world_product_session import _hash
    packaged["checksum"] = _hash(packaged["payload"])
    previous = product_restore(json.dumps(packaged))
    assert previous.living == s.living
    assert previous.terrain == s.terrain
    assert previous.society == s.society
    assert previous.cognition.day == 1
    assert not previous.cognition.bonds
    assert all(not m.memories for m in previous.cognition.minds)
    assert validate_product(previous)


def test_public_council_transfers_food_to_social_accountability():
    s = product(inhabitants=2)
    old_food = s.terrain.provisions
    s = act(s, "npc", "council")
    assert s.terrain.provisions == old_food - 1
    assert s.cognition.meetings == 1
    assert len(s.cognition.bonds) == 1
    assert s.cognition.bonds[0].trust == 1


def test_work_order_survives_player_transfer_and_original_source_turn():
    s = product(inhabitants=1)
    s = act(s, "npc", "commission", target=0, option="wood")
    s = act(s, "studio", "share_food")
    s = act(s, "causal", "end_turn")
    assert s.cognition.orders[0].kind == "wood"
    assert s.cognition.orders[0].status == "open"
    assert s.events == 3
    assert s.terrain.turns == s.society.tick == s.cognition.day == 1


def test_player_script_and_terminal_commands_expose_real_cognition(capsys):
    assert parse_command("npc commission 0 food 2", (0, 0)) == ProductAction(
        "npc", "commission", amount=2, target=0, option="food"
    )
    assert parse_command("npc cancel 1", (0, 0)).target == 1
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--system", "trophic", "--arc", "sandbox",
        "--inhabitants", "1",
        "--actions-json", '[{"layer":"npc","verb":"commission","target":0,'
                          '"option":"food"},{"layer":"causal","verb":"end_turn"},'
                          '{"layer":"causal","verb":"end_turn"}]',
        "--npc-report",
    ]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["product"]["npc_cognition"]["contracts"][0]["status"] == "fulfilled"
    assert printed["product"]["npc_cognition"]["verified_world_observations"] >= 1
    assert printed["product"]["world_turn"] == 2


def test_citizen_report_is_observational_not_mutating_player_save():
    s = product(inhabitants=5)
    before = product_save(s)
    report = cognition_report(s.cognition, s.society, s.terrain)
    assert report["citizens"] == 5
    assert report["report_not_an_llm"]
    assert product_save(s) == before
