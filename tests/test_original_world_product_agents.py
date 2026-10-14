"""Autonomous physical NPCs: actual local navigation, finite cargo and jobs."""
from __future__ import annotations
from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_product_terrain import (
    create_terrain, cell_at, terrain_save, terrain_restore,
)
from skeleton.game.generation.original_world_product_agents import (
    ROLES, Person, create_society, npc_tick, society_save,
    society_restore, validate_society,
)

DESIGN = "1" * 64


def test_twelve_professions_are_independent_persistent_people_not_a_population_meter() -> None:
    terrain = create_terrain(DESIGN)
    society = create_society(terrain)
    assert len(society.inhabitants) == 12
    assert {p.profession for p in society.inhabitants} == set(ROLES)
    assert all(not cell_at(terrain, p.x, p.y).blocking
               for p in society.inhabitants)
    assert [p.id for p in society.inhabitants] == list(range(12))


def test_every_tick_steps_real_npcs_at_most_one_passable_edge() -> None:
    terrain = create_terrain(DESIGN)
    population = create_society(terrain)
    for tick in range(5):
        previous = population.inhabitants
        terrain, population, receipts = npc_tick(terrain, population)
        assert len(receipts) == len(population.inhabitants) == 12
        assert population.tick == tick + 1
        for p, old in zip(population.inhabitants, previous):
            movement = abs(p.x - old.x) + abs(p.y - old.y)
            assert movement <= 1
            assert not cell_at(terrain, p.x, p.y).blocking
            assert 0 <= p.energy <= 20
            assert 0 <= p.health <= 20
            assert 0 <= p.hunger <= 20


def test_finite_food_production_and_delivery_conserve_provisions() -> None:
    world = create_terrain(DESIGN)
    society = create_society(world, count=1)
    initial = cell_at(world, 0, 0).food + world.provisions
    world, society, receipts = npc_tick(world, society)
    agent = society.inhabitants[0]
    assert agent.cargo == 1 and agent.cargo_kind == "food"
    assert cell_at(world, 0, 0).food == 2
    assert world.provisions + agent.cargo + cell_at(world, 0, 0).food == initial
    world, society, receipts = npc_tick(world, society)
    assert receipts[0].operation == "deliver"
    assert world.provisions == 6
    assert society.inhabitants[0].cargo == 0
    assert world.provisions + cell_at(world, 0, 0).food == initial


def test_several_decisions_remain_replay_deterministic_on_same_terrain() -> None:
    def simulate():
        world = create_terrain(DESIGN)
        agents = create_society(world)
        timeline = []
        for _ in range(9):
            world, agents, receipts = npc_tick(world, agents)
            timeline.append(receipts)
        return world, agents, tuple(timeline)

    assert simulate() == simulate()


def test_resident_conversations_and_professions_are_validated_and_saved() -> None:
    world = create_terrain(DESIGN)
    people = create_society(world, count=6)
    restored = society_restore(json.loads(json.dumps(society_save(people))), world)
    assert restored == people
    damaged = replace(people, inhabitants=(
        replace(people.inhabitants[0], cargo_kind="food", cargo=0),
        *people.inhabitants[1:],
    ))
    with pytest.raises(FoundationError):
        validate_society(damaged, world)


def test_physical_society_cannot_be_loaded_into_different_world_identity() -> None:
    one = create_terrain(DESIGN)
    people = create_society(one)
    other = create_terrain("3" * 64)
    with pytest.raises(FoundationError):
        society_restore(society_save(people), other)
    forged = society_save(people)
    forged["payload"]["tick"] = 99
    with pytest.raises(FoundationError):
        society_restore(forged, one)
