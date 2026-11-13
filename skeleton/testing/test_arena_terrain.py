"""Original seeded terrain generation must be canonical, traversable and replayable."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.arena_terrain import (
    _path, cli, generate_terrain, original_terrain, preview_terrain,
    verify_terrain,
)
from skeleton.game.gameplay.tactical_arena import normalize_arena, verify_arena
from skeleton.game.gameplay.turn_combat import CombatSessionError


@pytest.mark.parametrize("seed", [0, 1, 2, 311, 65535, 2147483647])
@pytest.mark.parametrize("density", [0, 10, 24, 40])
def test_original_terrain_is_seed_deterministic_and_traversable(seed, density):
    authored = original_terrain()
    authored.update(seed=seed, density=density)
    first = generate_terrain(authored)
    second = generate_terrain(copy.deepcopy(authored))
    assert first == second
    assert verify_terrain(json.loads(json.dumps(first))) == first
    assert normalize_arena(first["source"]) == first["source"]
    assert first["route"][0] == first["source"]["actors"][0]["position"]
    assert first["route"][-1] == first["source"]["actors"][1]["position"]
    assert len(first["route"]) == authored["width"]
    assert first["route"] == _path(first["source"])
    assert all(point not in first["source"]["walls"] for point in first["route"])


@pytest.mark.parametrize("width,height", [
    (4, 3), (7, 3), (9, 5), (16, 16), (32, 32),
])
def test_large_and_small_grids_keep_actor_route(width, height):
    authored = original_terrain()
    authored.update(width=width, height=height, density=40)
    terrain = generate_terrain(authored)
    assert len(terrain["route"]) == width
    assert len(terrain["source"]["walls"]) <= 512
    assert terrain["source"]["width"] == width
    assert terrain["source"]["height"] == height


def test_real_canonical_arena_autoplay_receipt():
    generated = generate_terrain(original_terrain())
    result = preview_terrain(generated)
    assert result["source_digest"] == generated["source_digest"]
    assert result["state_digest"] == result["session"]["state_digest"]
    assert result["phase"] in ("won", "draw", "lost")
    assert verify_arena(result["session"]) == result["session"]


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(seed=-1),
    lambda x: x.update(seed=True),
    lambda x: x.update(seed=2147483648),
    lambda x: x.update(width=3),
    lambda x: x.update(width=33),
    lambda x: x.update(height=2),
    lambda x: x.update(density=41),
    lambda x: x.update(turn_limit=0),
    lambda x: x.update(arena_id="../escape"),
    lambda x: x.update(schema_version="future"),
    lambda x: x.update(extra="ignored"),
])
def test_bad_generator_rejected(mutate):
    source = original_terrain()
    mutate(source)
    with pytest.raises(CombatSessionError):
        generate_terrain(source)


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x.update(generator_digest="0" * 64),
    lambda x: x.update(route_digest="0" * 64),
    lambda x: x["source"]["walls"].append([0, 0]),
    lambda x: x["route"].append([99, 99]),
    lambda x: x["generator"].update(seed=100),
])
def test_forged_generator_receipt_rejected(mutate):
    terrain = generate_terrain(original_terrain())
    bad = copy.deepcopy(terrain)
    mutate(bad)
    with pytest.raises(CombatSessionError):
        verify_terrain(bad)


def test_installed_terrain_cli(capsys):
    from skeleton.__main__ import main
    assert main(["arena-terrain", "demo"]) == 0
    generated = json.loads(capsys.readouterr().out)
    assert verify_terrain(generated) == generated
    assert cli(["verify", "--terrain-json", json.dumps(generated)]) == 0
    assert json.loads(capsys.readouterr().out) == generated
    assert cli(["preview", "--terrain-json", json.dumps(generated)]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["state_digest"] == preview["session"]["state_digest"]
    assert cli(["generate", "--generator-json", '{"bad":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
