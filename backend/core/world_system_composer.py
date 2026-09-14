"""Deterministic compiler from world topology into a runtime systems blueprint.

The compiler converts a generated world's observable topology into an explicit
DAG of simulation systems. It is renderer/storage neutral and emits a canonical
SHA-256 blueprint identity so identical worlds/configuration produce identical
system plans.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable


class WorldSystemCompositionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SystemNode:
    id: str
    phase: str
    requires: tuple[str, ...]
    enabled: bool = True
    reason: str = ""


@dataclass(frozen=True, slots=True)
class WorldSystemsBlueprint:
    version: int
    world_signature: str
    systems: tuple[SystemNode, ...]
    execution_order: tuple[str, ...]
    blueprint_sha256: str


_PHASE_ORDER = {"foundation": 0, "environment": 1, "simulation": 2, "population": 3, "gameplay": 4, "telemetry": 5}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _world_signature(world: dict[str, Any]) -> str:
    # Generated worlds can contain large tile arrays. The signature deliberately
    # covers the complete canonical payload so topology changes cannot alias.
    return _sha(world)


def _count(world: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = world.get(key)
        if isinstance(value, (list, tuple, dict, set)):
            return len(value)
        if isinstance(value, int):
            return max(0, value)
    stats = world.get("stats")
    if isinstance(stats, dict):
        for key in keys:
            value = stats.get(key)
            if isinstance(value, int):
                return max(0, value)
    return 0


def _has_water(world: dict[str, Any]) -> bool:
    stats = world.get("stats")
    if isinstance(stats, dict):
        for key in ("ocean_tiles", "river_tiles", "lakes", "water_tiles"):
            value = stats.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return True
    biomes = world.get("biomes")
    if isinstance(biomes, dict):
        return any(str(key) in {"ocean", "shallow", "lake", "river"} and bool(value) for key, value in biomes.items())
    return False


def _nodes(world: dict[str, Any]) -> tuple[SystemNode, ...]:
    settlements = _count(world, "settlements", "pois", "structures")
    entities = _count(world, "entities", "creatures", "population")
    has_water = _has_water(world)
    return (
        SystemNode("world.clock", "foundation", ()),
        SystemNode("world.spatial-index", "foundation", ()),
        SystemNode("environment.weather", "environment", ("world.clock",)),
        SystemNode("environment.terrain", "environment", ("world.spatial-index",)),
        SystemNode("environment.hydrology", "environment", ("environment.terrain",), has_water,
                   "enabled by detected water topology" if has_water else "no water topology detected"),
        SystemNode("simulation.physics", "simulation", ("environment.terrain", "world.clock")),
        SystemNode("simulation.navigation", "simulation", ("world.spatial-index", "environment.terrain")),
        SystemNode("population.settlements", "population", ("simulation.navigation",), settlements > 0,
                   f"{settlements} settlement/POI records"),
        SystemNode("population.agents", "population", ("simulation.navigation", "environment.weather"), entities > 0,
                   f"{entities} entity/population records"),
        SystemNode("gameplay.discovery", "gameplay", ("simulation.navigation",)),
        SystemNode("gameplay.travel", "gameplay", ("simulation.navigation", "environment.weather")),
        SystemNode("gameplay.economy", "gameplay", ("population.settlements",), settlements > 0,
                   "requires settlement topology"),
        SystemNode("telemetry.world", "telemetry", ("world.clock",)),
    )


def _topological_order(nodes: Iterable[SystemNode]) -> tuple[str, ...]:
    enabled = {node.id: node for node in nodes if node.enabled}
    for node in enabled.values():
        missing = [dep for dep in node.requires if dep not in enabled]
        if missing:
            raise WorldSystemCompositionError(f"enabled system {node.id} requires disabled/missing dependencies: {missing}")

    indegree = {node_id: 0 for node_id in enabled}
    children: dict[str, list[str]] = {node_id: [] for node_id in enabled}
    for node in enabled.values():
        for dep in node.requires:
            indegree[node.id] += 1
            children[dep].append(node.id)

    ready = sorted(
        (node_id for node_id, degree in indegree.items() if degree == 0),
        key=lambda node_id: (_PHASE_ORDER[enabled[node_id].phase], node_id),
    )
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort(key=lambda node_id: (_PHASE_ORDER[enabled[node_id].phase], node_id))

    if len(ordered) != len(enabled):
        unresolved = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
        raise WorldSystemCompositionError(f"world system graph contains a cycle: {unresolved}")
    return tuple(ordered)


def compose_world_systems(world: dict[str, Any]) -> WorldSystemsBlueprint:
    if not isinstance(world, dict) or not world:
        raise WorldSystemCompositionError("world payload must be a non-empty object")
    signature = _world_signature(world)
    systems = _nodes(world)
    order = _topological_order(systems)
    payload = {
        "version": 1,
        "world_signature": signature,
        "systems": [asdict(node) for node in systems],
        "execution_order": list(order),
    }
    return WorldSystemsBlueprint(
        version=1,
        world_signature=signature,
        systems=systems,
        execution_order=order,
        blueprint_sha256=_sha(payload),
    )


def blueprint_dict(blueprint: WorldSystemsBlueprint) -> dict[str, Any]:
    return {
        "version": blueprint.version,
        "world_signature": blueprint.world_signature,
        "systems": [asdict(node) for node in blueprint.systems],
        "execution_order": list(blueprint.execution_order),
        "blueprint_sha256": blueprint.blueprint_sha256,
    }
