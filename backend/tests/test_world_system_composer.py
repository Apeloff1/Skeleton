from dataclasses import replace

import pytest

from core.world_system_composer import (
    SystemNode,
    WorldSystemCompositionError,
    _topological_order,
    compose_world_systems,
)


def test_world_system_composition_is_deterministic():
    world = {
        "name": "Atlas",
        "stats": {"river_tiles": 12, "settlements": 3},
        "entities": [{"id": "a"}, {"id": "b"}],
    }
    first = compose_world_systems(world)
    second = compose_world_systems(world)
    assert first == second
    assert len(first.blueprint_sha256) == 64
    assert len(first.world_signature) == 64
    assert first.execution_order[0] in {"world.clock", "world.spatial-index"}


def test_water_and_population_enable_dependent_systems():
    world = {
        "stats": {"river_tiles": 5, "settlements": 2},
        "entities": [1],
    }
    blueprint = compose_world_systems(world)
    enabled = {node.id for node in blueprint.systems if node.enabled}
    assert "environment.hydrology" in enabled
    assert "population.settlements" in enabled
    assert "population.agents" in enabled
    assert "gameplay.economy" in enabled


def test_sparse_world_disables_optional_systems_without_breaking_dag():
    world = {"name": "Void", "stats": {"river_tiles": 0, "settlements": 0}}
    blueprint = compose_world_systems(world)
    enabled = {node.id for node in blueprint.systems if node.enabled}
    assert "environment.hydrology" not in enabled
    assert "population.settlements" not in enabled
    assert "gameplay.economy" not in enabled
    assert "gameplay.travel" in enabled


def test_world_mutation_changes_blueprint_identity():
    first = compose_world_systems({"stats": {"river_tiles": 0, "settlements": 1}})
    second = compose_world_systems({"stats": {"river_tiles": 1, "settlements": 1}})
    assert first.world_signature != second.world_signature
    assert first.blueprint_sha256 != second.blueprint_sha256


def test_empty_world_is_rejected():
    with pytest.raises(WorldSystemCompositionError, match="non-empty"):
        compose_world_systems({})


def test_dependency_cycle_is_rejected():
    nodes = (
        SystemNode("a", "foundation", ("b",)),
        SystemNode("b", "foundation", ("a",)),
    )
    with pytest.raises(WorldSystemCompositionError, match="cycle"):
        _topological_order(nodes)


def test_enabled_node_cannot_depend_on_disabled_node():
    nodes = (
        SystemNode("a", "foundation", (), enabled=False),
        SystemNode("b", "simulation", ("a",), enabled=True),
    )
    with pytest.raises(WorldSystemCompositionError, match="disabled/missing"):
        _topological_order(nodes)
