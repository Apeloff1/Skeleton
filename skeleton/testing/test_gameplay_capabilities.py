"""Contract, negative-input and replay tests for actual offline game building.

Tests use no model, external assets, network, training rows or filesystem
writes beyond explicit CLI fixture files in an isolated tmp directory.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest

from skeleton.ai.runtime.gameplay_capabilities import (
    GAMEPLAY_OPERATIONS, GameplayError, compile_level, compile_native_scene,
    generate_level,
    platformer_replay, platformer_step, tile_line_of_sight,
)
from skeleton.ai.runtime.deterministic_capabilities import (
    OPERATIONS, CapabilityTaskError, execute_capability_json,
    execute_capability_task,
)
from skeleton.ai.runtime.capability_graph import (
    SCHEMA as GRAPH_SCHEMA, execute_capability_graph,
)


W = [
    "#######",
    "#S...G#",
    "#.##..#",
    "#.....#",
    "#######",
]
CONTROLS = {"left": False, "right": False, "jump": False}


def test_six_additional_gameplay_capabilities_are_installed_without_model():
    assert set(GAMEPLAY_OPERATIONS) == {
        "game.level_generate", "game.level_compile", "game.scene_compile",
        "game.platformer_step", "game.platformer_replay",
        "game.tile_line_of_sight",
    }
    assert len(OPERATIONS) == 31
    assert set(GAMEPLAY_OPERATIONS).issubset(OPERATIONS)
    for name in GAMEPLAY_OPERATIONS:
        assert callable(OPERATIONS[name])


def test_level_compilation_is_engine_agnostic_and_reports_connected_graph():
    compiled = compile_level({"tiles": W})
    assert compiled["schema_version"] == "skeleton.gameplay.level.v1"
    assert compiled["width"] == 7 and compiled["height"] == 5
    assert compiled["spawn"] == {"x": 1, "y": 1}
    assert compiled["goal"] == {"x": 5, "y": 1}
    assert compiled["goal_reachable"] is True
    assert compiled["shortest_goal_steps"] == 4
    assert compiled["solid_count"] == sum(row.count("#") for row in W)
    assert compiled["walkable_count"] + compiled["solid_count"] == 35
    assert compiled["training_examples_added"] == 0
    assert compiled["proprietary_assets_embedded"] is False
    assert len(compiled["tile_digest"]) == 64


def test_disconnected_level_is_reported_not_falsely_promoted_to_valid():
    tiles = ["#####", "#S#G#", "#####", "#...#", "#####"]
    result = compile_level({"tiles": tiles})
    assert result["goal_reachable"] is False
    assert result["shortest_goal_steps"] is None
    assert result["reachable_from_spawn"] == 1


@pytest.mark.parametrize("seed", [0, 1, 17, 987654, 2**31 - 1])
@pytest.mark.parametrize("density", [0, 20, 50, 70])
def test_procedural_generation_is_deterministic_solvable_and_within_budget(seed, density):
    settings = {"seed": seed, "width": 20, "height": 14,
                "wall_percent": density}
    one = generate_level(settings)
    two = generate_level(settings)
    assert one == two
    assert len(one["tiles"]) == 14
    assert all(len(row) == 20 for row in one["tiles"])
    assert one["tiles"][1][1] == "S"
    assert one["tiles"][12][18] == "G"
    assert one["goal_reachable"] is True
    assert one["external_assets_used"] is False
    assert one["training_examples_added"] == 0
    compiled = compile_level({"tiles": one["tiles"]})
    assert compiled["goal_reachable"] is True
    assert compiled["tile_digest"] == one["tile_digest"]
    assert compiled["shortest_goal_steps"] == one["shortest_goal_steps"]


def test_seed_changes_map_contents_and_never_references_game_assets():
    settings = {"width": 24, "height": 16, "wall_percent": 55}
    generated = [
        generate_level({**settings, "seed": seed})
        for seed in range(8)
    ]
    assert len({item["tile_digest"] for item in generated}) >= 7
    assert all(item["training_examples_added"] == 0 for item in generated)
    assert all(item["external_assets_used"] is False for item in generated)


def test_platformer_discrete_gravity_is_replayable_and_collision_safe():
    initial = {"x": 1, "y": 1, "vx": 0, "vy": 0}
    falling = platformer_step({
        "tiles": W, "avatar": initial, "control": CONTROLS,
    })
    assert falling["avatar"]["x"] == 1
    assert falling["avatar"]["y"] == 2
    assert falling["avatar"]["vy"] == 1
    assert falling["goal_reached"] is False
    assert falling["grounded"] is False
    landing = platformer_step({
        "tiles": W, "avatar": falling["avatar"], "control": CONTROLS,
    })
    assert landing["avatar"]["y"] == 3
    assert landing["avatar"]["vy"] == 0
    assert landing["grounded"] is True
    jumping = platformer_step({
        "tiles": W, "avatar": landing["avatar"],
        "control": {"left": False, "right": True, "jump": True},
    })
    assert jumping["avatar"]["y"] == 3  # Row 2 at x2 is a wall: no jump-through
    assert jumping["avatar"]["x"] == 2
    assert jumping["avatar"]["vy"] == 0


def test_platformer_replay_returns_stable_digest_without_mutation():
    avatar = {"x": 1, "y": 1, "vx": 0, "vy": 0}
    actions = [dict(CONTROLS) for _ in range(8)]
    before = json.dumps({"avatar": avatar, "actions": actions})
    a = platformer_replay({"tiles": W, "avatar": avatar, "controls": actions})
    b = platformer_replay({"tiles": W, "avatar": avatar, "controls": actions})
    assert a == b
    assert json.dumps({"avatar": avatar, "actions": actions}) == before
    assert a["frames_simulated"] == 8
    assert len(a["trace"]) == 8
    assert a["final_avatar"]["y"] == 3
    assert a["goal_first_reached_frame"] is None
    assert a["training_examples_added"] == 0
    assert a["trained_model_used"] is False
    assert len(a["trace_sha256"]) == 64


def test_high_speed_vertical_motion_cannot_tunnel_through_walls():
    avatar = {"x": 1, "y": 1, "vx": 0, "vy": 4}
    result = platformer_step({
        "tiles": W, "avatar": avatar, "control": CONTROLS,
    })
    assert result["avatar"]["y"] == 3
    assert result["avatar"]["vy"] == 0
    assert result["grounded"] is True


def test_goal_crossing_is_detected_and_remains_deterministic():
    # Directly pass a controlled avatar adjacent to its goal with no walls.
    avatar = {"x": 4, "y": 1, "vx": 0, "vy": 0}
    data = {
        "tiles": W, "avatar": avatar,
        "control": {"left": False, "right": True, "jump": False},
    }
    result = platformer_step(data)
    assert result["avatar"]["x"] == 5
    assert result["goal_reached"] is True


def test_line_of_sight_blocks_wall_and_closed_diagonal_corners():
    open_view = tile_line_of_sight({
        "tiles": W, "start": {"x": 1, "y": 1},
        "goal": {"x": 5, "y": 1},
    })
    assert open_view["visible"] is True
    assert open_view["blocked_at"] is None
    assert len(open_view["cells_examined"]) == 5
    blocked = tile_line_of_sight({
        "tiles": W, "start": {"x": 1, "y": 3},
        "goal": {"x": 3, "y": 1},
    })
    assert blocked["visible"] is False
    assert blocked["blocked_at"] is not None
    assert len(blocked["cells_examined"]) <= 5


@pytest.mark.parametrize(("operation", "args"), [
    ("game.level_generate", {"seed": 1, "width": True,
                             "height": 7, "wall_percent": 40}),
    ("game.level_generate", {"seed": -1, "width": 7,
                             "height": 7, "wall_percent": 40}),
    ("game.level_generate", {"seed": 1, "width": 7,
                             "height": 7, "wall_percent": 90}),
    ("game.level_compile", {"tiles": ["#####", "#S.G#", "#...#", "####"]}),
    ("game.level_compile", {"tiles": ["#####", "#S.S#", "#.G.#",
                                     "#...#", "#####"]}),
    ("game.level_compile", {"tiles": ["#####", "#S.Z#", "#.G.#",
                                     "#...#", "#####"]}),
    ("game.level_compile", {"tiles": [["#", "S", "G"]]}),
    ("game.platformer_step", {"tiles": W, "avatar": {
        "x": 1, "y": 1, "vx": 0, "vy": 0,
    }, "control": {"left": 1, "right": False, "jump": False}}),
    ("game.platformer_step", {"tiles": W, "avatar": {
        "x": 0, "y": 0, "vx": 0, "vy": 0,
    }, "control": CONTROLS}),
    ("game.platformer_replay", {"tiles": W, "avatar": {
        "x": 1, "y": 1, "vx": 0, "vy": 0,
    }, "controls": []}),
    ("game.platformer_replay", {"tiles": W, "avatar": {
        "x": 1, "y": 1, "vx": 0, "vy": 0,
    }, "controls": [CONTROLS] * 65}),
    ("game.tile_line_of_sight", {"tiles": W, "start": {
        "x": -1, "y": 1,
    }, "goal": {"x": 5, "y": 1}}),
])
def test_game_capabilities_fail_closed_for_invalid_inputs(operation, args):
    with pytest.raises((GameplayError, CapabilityTaskError)):
        execute_capability_task({"operation": operation, "args": args})


def test_game_operations_reject_extra_authority_fields():
    with pytest.raises(GameplayError):
        generate_level({
            "seed": 1, "width": 8, "height": 8,
            "wall_percent": 30, "network": True,
        })
    with pytest.raises(GameplayError):
        platformer_step({
            "tiles": W, "avatar": {"x": 1, "y": 1, "vx": 0, "vy": 0},
            "control": {**CONTROLS, "execute": "/bin/sh"},
        })


def test_generated_level_feeds_compiler_then_simulation_in_capability_graph():
    graph = {
        "schema_version": GRAPH_SCHEMA,
        "nodes": [
            {"id": "level", "operation": "game.level_generate",
             "args": {"seed": 1729, "width": 10, "height": 8,
                      "wall_percent": 50}},
            {"id": "compiled", "operation": "game.level_compile",
             "args": {"tiles": {"$ref": "level", "path": ["tiles"]}}},
            {"id": "step", "operation": "game.platformer_step",
             "args": {
                 "tiles": {"$ref": "compiled", "path": ["tiles"]},
                 "avatar": {"x": 1, "y": 1, "vx": 0, "vy": 0},
                 "control": {"left": False, "right": True, "jump": False},
             }},
        ],
        "outputs": ["compiled", "step"],
    }
    receipt = execute_capability_graph(graph)
    assert receipt["node_count"] == 3
    assert receipt["outputs"]["compiled"]["goal_reachable"] is True
    assert receipt["outputs"]["step"]["avatar"]["x"] >= 1
    assert receipt["training_examples_added"] == 0
    assert receipt["model_inference_used"] is False
    assert receipt["network_access_used"] is False


def test_inference_free_capability_cli_and_unified_entrypoint(
    tmp_path: Path, capsys,
):
    from skeleton.app.offline_cli import main as offline_console
    from skeleton.app.cli import run_app_cli

    inp = tmp_path / "level.json"
    inp.write_text(json.dumps({
        "operation": "game.level_generate",
        "args": {"seed": 4, "width": 12,
                 "height": 8, "wall_percent": 40},
    }), encoding="utf-8")
    assert offline_console(["--capability-file", str(inp), "--json"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["operation"] == "game.level_generate"
    assert receipt["result"]["goal_reachable"] is True
    assert receipt["result"]["training_examples_added"] == 0
    assert len(receipt["result"]["tiles"]) == 8
    assert run_app_cli([
        "local-ai", "--capability-file", str(inp), "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == receipt


def test_procedural_level_generation_is_resource_bounded_and_replay_stable():
    randomizer = random.Random(1729)
    for _ in range(24):
        w, h = randomizer.randint(5, 32), randomizer.randint(5, 32)
        level = generate_level({
            "seed": randomizer.randint(0, 2**31 - 1),
            "width": w, "height": h,
            "wall_percent": randomizer.randint(0, 70),
        })
        # Worst-case tilemaps should be smaller than the 8-KiB task
        # admission bound and produce valid engine-neutral level output.
        serialized = json.dumps(level)
        assert len(serialized) < 8192
        assert level["goal_reachable"]
        assert compile_level({"tiles": level["tiles"]})["goal_reachable"]


def test_engine_neutral_scene_packs_wall_runs_without_losing_geometry():
    scene = compile_native_scene({"tiles": W})
    level = compile_level({"tiles": W})
    assert scene["schema_version"] == "skeleton.gameplay.engine_neutral_scene.v1"
    assert scene["coordinate_system"] == "integer_grid_y_down"
    assert scene["tile_size"] == 1
    assert scene["width"] == 7 and scene["height"] == 5
    assert scene["source_tile_digest"] == level["tile_digest"]
    assert scene["goal_reachable"] is True
    assert scene["solid_tiles_covered"] == level["solid_count"]
    assert scene["collider_count"] < scene["solid_tiles_covered"]
    assert scene["entities"] == [
        {"id": "player", "kind": "controllable_actor",
         "position": {"x": 1, "y": 1},
         "velocity": {"x": 0, "y": 0}},
        {"id": "goal", "kind": "goal_trigger",
         "position": {"x": 5, "y": 1}},
    ]
    assert scene["native_executable_created"] is False
    assert scene["external_artwork_included"] is False
    assert scene["training_examples_added"] == 0
    cells = {
        (x, rect["y"])
        for rect in scene["collider_rectangles"]
        for x in range(rect["x"], rect["x"] + rect["width"])
    }
    expected = {(x, y) for y, line in enumerate(W)
                for x, ch in enumerate(line) if ch == "#"}
    assert cells == expected


def test_compiled_scene_large_checkerboard_still_within_receipt_budget():
    rows = []
    for y in range(32):
        rows.append("".join("#" if (x + y) % 2 else "."
                            for x in range(32)))
    rows[1] = rows[1][:1] + "S" + rows[1][2:]
    rows[30] = rows[30][:30] + "G" + rows[30][31:]
    receipt = execute_capability_task({
        "operation": "game.scene_compile", "args": {"tiles": rows},
    })
    scene = receipt["result"]
    assert scene["solid_tiles_covered"] == sum(row.count("#") for row in rows)
    assert scene["collider_count"] <= 512
    assert len(json.dumps(receipt, sort_keys=True).encode("utf-8")) < 32768


def test_graph_compiles_seeded_map_into_engine_neutral_scene_without_assets():
    graph = {
        "schema_version": GRAPH_SCHEMA,
        "nodes": [
            {"id": "map", "operation": "game.level_generate",
             "args": {"seed": 7, "width": 8, "height": 7,
                      "wall_percent": 25}},
            {"id": "scene", "operation": "game.scene_compile",
             "args": {"tiles": {"$ref": "map", "path": ["tiles"]}}},
        ],
        "outputs": ["scene"],
    }
    result = execute_capability_graph(graph)
    scene = result["outputs"]["scene"]
    assert result["node_count"] == 2
    assert scene["goal_reachable"] is True
    assert scene["training_examples_added"] == 0
    assert scene["native_executable_created"] is False
    assert len(scene["entities"]) == 2
