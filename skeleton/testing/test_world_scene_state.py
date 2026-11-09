"""Deterministic world/scene state graph contracts for issue #945."""

from __future__ import annotations

import ast
from collections import deque
from pathlib import Path

import pytest

from skeleton.world import (
    MAX_CHILDREN,
    MAX_DEPTH,
    MAX_ENTITIES,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    Transform,
    WorldBoundError,
    WorldCycleError,
    WorldOrphanError,
    WorldReferenceError,
    WorldSchemaError,
    WorldState,
    WorldTimeError,
    diagnose_payload,
)

WORLD_ROOT = Path(__file__).resolve().parents[1] / "world"
BANNED_IMPORTS = {
    "godot",
    "godot_engine",
    "pygame",
    "panda3d",
    "socket",
    "http",
    "http.client",
    "urllib",
    "requests",
    "httpx",
    "websocket",
    "asyncio",
}


def _world(tick: int = 0, **limits: int) -> WorldState:
    return WorldState("world_alpha", tick=tick, **limits)


def _tree() -> WorldState:
    world = _world()
    world.spawn("room", kind="node", tick=1)
    world.spawn("table", kind="node", tick=1, parent_id="room")
    world.spawn("lamp", kind="prop", tick=2, parent_id="table")
    world.spawn("chair", kind="prop", tick=2, parent_id="room")
    return world


def test_stable_ids_and_schema_version_are_part_of_the_contract():
    world = _tree()

    assert world.schema == SCHEMA_NAME == "world.scene_state.v1"
    assert world.schema_version == SCHEMA_VERSION == 1
    assert world.world_id == "world_alpha"
    assert world.traverse() == ("room", "table", "lamp", "chair")
    assert world.require("lamp").entity_id == "lamp"
    payload = world.to_payload()
    assert payload["schema"] == SCHEMA_NAME
    assert payload["schema_version"] == SCHEMA_VERSION
    assert [item["entity_id"] for item in payload["entities"]] == ["chair", "lamp", "room", "table"]


def test_hierarchy_edits_reparent_reorder_and_cascade_remove():
    world = _tree()
    world.reparent("lamp", "room", tick=3)
    assert world.parent("lamp") == "room"
    assert world.children("room") == ("table", "chair", "lamp")
    assert world.roots() == ("room",)

    world.set_sibling_index("chair", 0, tick=3)
    assert world.children("room") == ("chair", "table", "lamp")
    world.set_sibling_index("lamp", 1, tick=4)
    assert world.children("room") == ("chair", "lamp", "table")
    assert world.traverse() == ("room", "chair", "lamp", "table")

    removed = world.remove("lamp", tick=5, cascade=True)
    assert removed == ("lamp",)
    assert world.traverse() == ("room", "chair", "table")
    assert world.get("lamp") is None

    with pytest.raises(WorldOrphanError, match="orphan children"):
        world.remove("room", tick=6)
    removed = world.remove("room", tick=6, cascade=True)
    assert removed == ("room", "chair", "table")
    assert world.entity_count == 0
    assert world.roots() == ()


def test_invalid_references_fail_closed():
    world = _world()
    world.spawn("root", kind="node", tick=0)

    with pytest.raises(WorldReferenceError, match="unknown parent"):
        world.spawn("child", kind="node", tick=1, parent_id="missing")
    with pytest.raises(WorldReferenceError, match="unknown entity"):
        world.require("missing")
    with pytest.raises(WorldReferenceError, match="unknown entity"):
        world.reparent("missing", "root", tick=1)
    with pytest.raises(WorldReferenceError, match="unknown parent"):
        world.reparent("root", "missing", tick=1)
    with pytest.raises(WorldReferenceError, match="unknown entity"):
        world.remove("missing", tick=1)

    payload = world.to_payload()
    payload["entities"][0]["child_ids"] = ["ghost"]
    diagnosis = diagnose_payload(payload)
    assert "invalid_reference" in diagnosis.issues
    assert diagnosis.invalid_references == ("ghost",)
    with pytest.raises(WorldReferenceError):
        WorldState.from_payload(payload)


def test_cycles_are_detected_and_rejected():
    world = _tree()
    with pytest.raises(WorldCycleError, match="cycle"):
        world.reparent("room", "lamp", tick=3)
    with pytest.raises(WorldCycleError, match="parent itself"):
        world.reparent("room", "room", tick=3)
    assert world.detect_cycles() == ()
    assert world.diagnose().ok

    payload = world.to_payload()
    by_id = {item["entity_id"]: item for item in payload["entities"]}
    by_id["room"]["parent_id"] = "lamp"
    by_id["room"]["child_ids"] = ["table", "chair"]
    by_id["lamp"]["child_ids"] = ["room"]
    payload["roots"] = []
    diagnosis = diagnose_payload(payload)
    assert "cycle" in diagnosis.issues
    assert diagnosis.cycles
    with pytest.raises(WorldCycleError):
        WorldState.from_payload(payload)


def test_orphan_detection_on_dangling_parent_payload():
    world = _tree()
    payload = world.to_payload()
    by_id = {item["entity_id"]: item for item in payload["entities"]}
    by_id["lamp"]["parent_id"] = "attic"
    by_id["table"]["child_ids"] = []
    diagnosis = diagnose_payload(payload)
    assert "orphan" in diagnosis.issues or "dangling_parent" in diagnosis.issues
    assert "lamp" in diagnosis.orphans or "attic" in diagnosis.invalid_references
    with pytest.raises((WorldOrphanError, WorldReferenceError)):
        WorldState.from_payload(payload)


def test_traversal_and_serialization_ordering_are_deterministic():
    first = _tree()
    second = _tree()
    assert first.traverse() == second.traverse() == ("room", "table", "lamp", "chair")
    assert first.to_bytes() == second.to_bytes()
    assert first.digest() == second.digest()

    scrambled = WorldState("world_alpha")
    scrambled.spawn("room", kind="node", tick=1)
    scrambled.spawn("chair", kind="prop", tick=1, parent_id="room")
    scrambled.spawn("table", kind="node", tick=1, parent_id="room")
    scrambled.spawn("lamp", kind="prop", tick=2, parent_id="table")
    assert scrambled.children("room") == ("chair", "table")
    assert scrambled.traverse() != first.traverse()
    assert scrambled.digest() != first.digest()
    payload = first.to_payload()
    assert [item["entity_id"] for item in payload["entities"]] == sorted(
        item["entity_id"] for item in payload["entities"]
    )


def test_persistence_round_trip_preserves_hierarchy_and_digest():
    world = _tree()
    world.set_transform("lamp", Transform(translation=(1.5, 0.0, -2.0)), tick=3)
    world.set_attributes("room", {"biome": "interior", "lit": True}, tick=3)
    restored = WorldState.from_bytes(world.to_bytes())

    assert restored.digest() == world.digest()
    assert restored.traverse() == world.traverse()
    assert restored.children("room") == world.children("room")
    assert restored.require("lamp").transform.translation == (1.5, 0.0, -2.0)
    assert dict(restored.require("room").attributes) == {"biome": "interior", "lit": True}
    assert restored.tick == world.tick == 3
    assert restored.revision == world.revision
    assert restored.schema_version == SCHEMA_VERSION


def test_version_mismatch_and_unknown_fields_fail_closed():
    payload = _tree().to_payload()
    payload["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(WorldSchemaError, match="schema mismatch"):
        WorldState.from_payload(payload)

    payload = _tree().to_payload()
    payload["schema"] = "world.scene_state.v0"
    with pytest.raises(WorldSchemaError, match="schema mismatch"):
        WorldState.from_payload(payload)

    payload = _tree().to_payload()
    payload["renderer"] = "godot"
    with pytest.raises(WorldSchemaError, match="schema mismatch"):
        WorldState.from_payload(payload)

    payload = _tree().to_payload()
    del payload["schema_version"]
    with pytest.raises(WorldSchemaError):
        WorldState.from_payload(payload)


def test_large_bounded_graphs_reject_overflow_and_stay_deterministic():
    world = WorldState("arena", max_entities=MAX_ENTITIES, max_children=MAX_CHILDREN)
    world.spawn("origin", kind="node", tick=0)
    frontier: deque[str] = deque(["origin"])
    spawned = 1
    tick = 1
    while spawned < MAX_ENTITIES:
        parent_id = frontier[0]
        depth = len(world.ancestors(parent_id))
        if len(world.children(parent_id)) >= MAX_CHILDREN or depth >= MAX_DEPTH:
            frontier.popleft()
            continue
        entity_id = f"n{spawned:04d}"
        world.spawn(entity_id, kind="node", tick=tick, parent_id=parent_id)
        frontier.append(entity_id)
        spawned += 1
        if spawned % 32 == 0:
            tick += 1

    assert world.entity_count == MAX_ENTITIES
    with pytest.raises(WorldBoundError, match="entity bound"):
        world.spawn("overflow", kind="node", tick=tick + 1, parent_id="origin")

    walk = world.traverse()
    assert len(walk) == MAX_ENTITIES
    assert len(set(walk)) == MAX_ENTITIES
    assert all(len(world.ancestors(entity_id)) <= MAX_DEPTH for entity_id in walk)
    restored = WorldState.from_bytes(world.to_bytes())
    assert restored.digest() == world.digest()
    assert restored.traverse() == walk
    assert restored.diagnose().ok


def test_explicit_time_is_required_and_monotonic():
    world = _world(tick=4)
    with pytest.raises(TypeError):
        world.spawn("root", kind="node")  # type: ignore[call-arg]
    with pytest.raises(WorldTimeError, match="monotonic"):
        world.spawn("root", kind="node", tick=3)
    with pytest.raises(WorldTimeError):
        world.spawn("root", kind="node", tick=-1)
    with pytest.raises(WorldTimeError):
        world.spawn("root", kind="node", tick=True)  # type: ignore[arg-type]
    entity = world.spawn("root", kind="node", tick=4)
    assert entity.created_tick == 4
    assert world.tick == 4
    world.spawn("child", kind="node", tick=9, parent_id="root")
    assert world.tick == 9


def test_child_and_depth_bounds_fail_closed():
    world = WorldState("narrow", max_entities=8, max_children=2, max_depth=2)
    world.spawn("root", kind="node", tick=0)
    world.spawn("a", kind="node", tick=1, parent_id="root")
    world.spawn("b", kind="node", tick=1, parent_id="root")
    with pytest.raises(WorldBoundError, match="child bound"):
        world.spawn("c", kind="node", tick=1, parent_id="root")
    world.spawn("leaf", kind="node", tick=2, parent_id="a")
    with pytest.raises(WorldBoundError, match="depth bound"):
        world.spawn("too_deep", kind="node", tick=3, parent_id="leaf")


def test_module_is_engine_neutral_and_stdlib_only():
    imported: set[str] = set()
    for path in sorted(WORLD_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
                imported.add(node.module)
    assert imported.isdisjoint(BANNED_IMPORTS)
    assert "godot" not in imported
    assert "skeleton.game" not in imported
    assert "skeleton.forge" not in imported
    assert "skeleton.frontier" not in imported
    source = (WORLD_ROOT / "scene.py").read_text(encoding="utf-8")
    assert "time.time" not in source
    assert "uuid4" not in source
    assert "datetime" not in source
