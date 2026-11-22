"""Adversarial source validation for Cinder Ridge."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from skeleton.game.gameplay.ridge_rescue.schema import parse_world, world_dict, WorldError

SOURCE = Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue/cinder_ridge.json"

def data():
    return json.loads(SOURCE.read_text())

def test_original_world_is_bounded_and_canonical():
    world = parse_world(SOURCE.read_bytes())
    assert world.width == 9
    assert world.height == 7
    assert len(world.civilians) == 2
    assert world_dict(parse_world(world_dict(world))) == world_dict(world)

@pytest.mark.parametrize("key,value", [
    ("schema", "ridge.rescue.world.v2"), ("rows", ["..", "..."]),
    ("start", [99, 0]), ("start", [True, 0]), ("max_turns", True),
    ("max_turns", 10000), ("max_turns", 1), ("civilians", []),
])
def test_bad_world_fields_fail_closed(key, value):
    source = data()
    source[key] = value
    with pytest.raises(WorldError):
        parse_world(source)

def test_rejects_duplicate_actor_positions_and_ids():
    source = data()
    source["raiders"][0]["id"] = source["civilians"][0]["id"]
    with pytest.raises(WorldError):
        parse_world(source)
    source = data()
    source["raiders"][0]["at"] = source["civilians"][0]["at"]
    with pytest.raises(WorldError):
        parse_world(source)

def test_rejects_resource_collision_and_bad_quantity():
    source = data()
    source["resources"][0]["at"] = source["start"]
    with pytest.raises(WorldError):
        parse_world(source)
    source = data()
    source["resources"][0]["count"] = -1
    with pytest.raises(WorldError):
        parse_world(source)

def test_rejects_unsafe_source_sizes_and_unknown_fields():
    with pytest.raises(WorldError):
        parse_world(b" " * 96001)
    source = data()
    source["arbitrary"] = "unsafe"
    with pytest.raises(WorldError):
        parse_world(source)
    with pytest.raises(WorldError):
        parse_world(b"\xff")
