"""Adversarial and functional tests for model-free offline capabilities."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest

from skeleton.ai.runtime.deterministic_capabilities import (
    CapabilityTaskError, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, OPERATIONS,
    execute_capability_json, execute_capability_task,
)


def run(operation: str, **kwargs):
    receipt = execute_capability_task({"operation": operation, "args": kwargs})
    assert receipt["schema_version"] == "skeleton.offline_deterministic_capabilities.v1"
    assert receipt["operation"] == operation
    for key in ("deterministic",):
        assert receipt[key] is True
    for key in ("model_inference_used", "network_access_used",
                "filesystem_access_used", "authority_granted"):
        assert receipt[key] is False
    canonical = json.dumps(
        receipt["result"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")
    assert receipt["result_sha256"] == hashlib.sha256(canonical).hexdigest()
    return receipt["result"]


def test_all_24_capabilities_are_reachable_without_training_or_model_inference():
    assert len(OPERATIONS) == 31
    assert set(OPERATIONS) == {
        "math.add", "math.multiply", "math.sum", "grid.move",
        "grid.neighbors", "grid.manhattan", "grid.shortest_path",
        "physics.advance_1d", "physics.integrate_2d",
        "collision.aabb", "collision.point_rect",
        "state.transition", "inventory.update", "game.damage",
        "game.coins", "game.cooldown", "game.animation_frame",
        "events.order", "events.elapsed", "json.select",
        "text.normalize", "policy.local_action", "evidence.lookup",
        "content.sha256",
        "game.level_generate", "game.level_compile", "game.scene_compile",
        "game.playability_check",
        "game.platformer_step",
        "game.platformer_replay", "game.tile_line_of_sight",
    }


@pytest.mark.parametrize(("op", "args", "expected"), [
    ("math.add", {"a": 12, "b": 30}, 42),
    ("math.multiply", {"a": -7, "b": 6}, -42),
    ("math.sum", {"values": [9, -3, 1]}, 7),
    ("grid.move", {"position": {"x": 1, "y": 4}, "delta": {"x": -2, "y": 7}},
     {"x": -1, "y": 11}),
    ("grid.neighbors", {"position": {"x": 0, "y": 0}, "width": 3, "height": 3},
     [{"x": 1, "y": 0}, {"x": 0, "y": 1}]),
    ("grid.manhattan", {"start": {"x": 5, "y": -1}, "goal": {"x": 1, "y": 2}}, 7),
    ("physics.advance_1d", {"position": 5, "velocity": -2, "ticks": 3}, -1),
    ("physics.integrate_2d", {
        "position": {"x": 1, "y": 2}, "velocity": {"x": 2, "y": -1},
        "acceleration": {"x": 1, "y": 2}, "ticks": 3,
    }, {"position": {"x": 13, "y": 11}, "velocity": {"x": 5, "y": 5}, "ticks": 3}),
    ("state.transition", {"state": "idle", "event": "start"}, "running"),
    ("state.transition", {"state": "idle", "event": "pause"}, "idle"),
    ("inventory.update", {
        "current": 10, "maximum": 20, "action": "add", "quantity": 5,
    }, {"accepted": True, "remaining": 15}),
    ("inventory.update", {
        "current": 10, "maximum": 20, "action": "remove", "quantity": 11,
    }, {"accepted": False, "remaining": 10}),
    ("game.damage", {"health": 2, "damage": 100}, 0),
    ("game.coins", {"coins": 5, "points_per_coin": 10}, 50),
    ("game.cooldown", {"frames": 8, "elapsed": 10}, 0),
    ("game.animation_frame", {"tick": 13, "frames": 4, "ticks_per_frame": 3}, 0),
    ("events.order", {"events": [
        {"name": "late", "tick": 8}, {"name": "early", "tick": 1},
        {"name": "sameA", "tick": 3}, {"name": "sameB", "tick": 3},
    ]}, ["early", "sameA", "sameB", "late"]),
    ("events.elapsed", {"start_tick": 5, "end_tick": 20}, 15),
    ("json.select", {"object": {"health": 8, "x": 2}, "keys": ["x", "health"]},
     {"x": 2, "health": 8}),
    ("text.normalize", {"text": "HELLO,  SCENE_12 / WORLD!!"}, "hello scene_12 world"),
    ("policy.local_action", {"action": "fetch_url", "operator_selected": True},
     {"policy_allow": False, "executor_permission_granted": False}),
    ("policy.local_action", {"action": "read_local_text", "operator_selected": True},
     {"policy_allow": True, "executor_permission_granted": False}),
    ("evidence.lookup", {"facts": {"period": 8}, "key": "period"},
     {"found": True, "value": 8, "source_trusted": False}),
    ("evidence.lookup", {"facts": {"period": 8}, "key": "absent"},
     {"found": False, "value": None, "source_trusted": False}),
    ("content.sha256", {"text": "abc"},
     hashlib.sha256(b"abc").hexdigest()),
])
def test_operation_reference_examples(op, args, expected):
    assert run(op, **args) == expected


def test_aabb_is_half_open_and_symmetric_with_edge_touch_not_collision():
    left = {"x0": 0, "y0": 0, "x1": 4, "y1": 4}
    overlapping = {"x0": 3, "y0": 3, "x1": 6, "y1": 7}
    touching = {"x0": 4, "y0": 1, "x1": 6, "y1": 2}
    assert run("collision.aabb", a=left, b=overlapping) is True
    assert run("collision.aabb", a=overlapping, b=left) is True
    assert run("collision.aabb", a=left, b=touching) is False
    assert run("collision.point_rect", point={"x": 0, "y": 0}, rect=left) is True
    assert run("collision.point_rect", point={"x": 4, "y": 0}, rect=left) is False


def test_pathfinding_shortest_walk_avoids_obstacles_and_is_deterministic():
    source = {"x": 0, "y": 0}
    target = {"x": 3, "y": 0}
    obstacles = [{"x": 1, "y": 0}, {"x": 2, "y": 0}]
    args = dict(start=source, goal=target, width=4, height=4, blocked=obstacles)
    path = run("grid.shortest_path", **args)
    assert path["reachable"] is True
    assert path["steps"] == 5
    assert path["path"][0] == source
    assert path["path"][-1] == target
    for a, b in zip(path["path"], path["path"][1:]):
        assert abs(a["x"] - b["x"]) + abs(a["y"] - b["y"]) == 1
        assert b not in obstacles
    assert path == run("grid.shortest_path", **args)


def test_pathfinding_handles_disconnected_and_zero_length_routes():
    start = {"x": 0, "y": 0}
    end = {"x": 2, "y": 0}
    blocked = [{"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 1, "y": 2}]
    unreachable = run(
        "grid.shortest_path", start=start, goal=end,
        width=3, height=3, blocked=blocked,
    )
    assert unreachable == {"reachable": False, "steps": None, "path": []}
    same = run(
        "grid.shortest_path", start=start, goal=start,
        width=3, height=3, blocked=[],
    )
    assert same == {"reachable": True, "steps": 0, "path": [start]}


def test_simple_property_based_motion_and_addition_reference_without_external_dependencies():
    rng = random.Random(713_902)
    for _ in range(120):
        a, b = rng.randint(-1000, 1000), rng.randint(-1000, 1000)
        assert run("math.add", a=a, b=b) == a + b
        assert run("math.multiply", a=a, b=b) == a * b
        ticks = rng.randint(0, 100)
        assert run("physics.advance_1d", position=a, velocity=b, ticks=ticks) == a + b * ticks
        acceleration = rng.randint(-15, 15)
        actual = run(
            "physics.integrate_2d",
            position={"x": a, "y": b},
            velocity={"x": b, "y": a},
            acceleration={"x": acceleration, "y": -acceleration},
            ticks=ticks,
        )
        # Independent iterative Euler oracle; bounded loop 100 ticks.
        px, py, vx, vy = a, b, b, a
        for _tick in range(ticks):
            vx += acceleration
            vy -= acceleration
            px += vx
            py += vy
        assert actual["position"] == {"x": px, "y": py}
        assert actual["velocity"] == {"x": vx, "y": vy}


@pytest.mark.parametrize(("op", "args"), [
    ("math.add", {"a": True, "b": 1}),
    ("math.sum", {"values": [0, 1.3]}),
    ("grid.neighbors", {"position": {"x": -1, "y": 0}, "width": 2, "height": 2}),
    ("grid.shortest_path", {"start": {"x": 0, "y": 0},
                            "goal": {"x": 1, "y": 1},
                            "width": 3, "height": 3,
                            "blocked": [{"x": 9, "y": 9}]}),
    ("physics.integrate_2d", {"position": {"x": 0, "y": 0},
                               "velocity": {"x": 0, "y": 0},
                               "acceleration": {"x": 0, "y": 0},
                               "ticks": -1}),
    ("collision.aabb", {"a": {"x0": 0, "y0": 0, "x1": 0, "y1": 1},
                        "b": {"x0": 0, "y0": 0, "x1": 1, "y1": 1}}),
    ("state.transition", {"state": "admin", "event": "start"}),
    ("inventory.update", {"current": 10, "maximum": 8, "action": "add", "quantity": 1}),
    ("events.elapsed", {"start_tick": 10, "end_tick": 4}),
    ("json.select", {"object": {"a": 1}, "keys": [None]}),
    ("json.select", {"object": {"a": 1}, "keys": ["a", "a"]}),
    ("policy.local_action", {"action": "execute_binary", "operator_selected": 1}),
    ("evidence.lookup", {"facts": [], "key": "p"}),
    ("content.sha256", {"text": "\x00secret"}),
])
def test_invalid_operation_arguments_fail_closed(op, args):
    with pytest.raises(CapabilityTaskError):
        run(op, **args)


def test_nested_json_attack_payloads_rejected_before_execution():
    payloads = [
        b'{"operation":"math.add","operation":"math.multiply","args":{"a":1,"b":2}}',
        b'{"operation":"math.add","args":{"a":1,"a":9,"b":2}}',
        b'{"operation":"math.add","args":{"a":NaN,"b":2}}',
        b'{"operation":"math.add","args":{"a":Infinity,"b":2}}',
        b'{"operation":"math.add","args":{"a":1.0,"b":2}}',
        b'{"operation":"os.system","args":{}}',
        b'[{"operation":"math.add","args":{"a":1,"b":2}}]',
        b'{"operation":"math.add","args":{"a":1,"b":2}, "extra":"request"}',
        b'{"operation":"math.add","args":{"a":1,"b":2}}' + b' ' * MAX_INPUT_BYTES,
        b'\xff\xff',
        b'{"operation":"math.add","args":{"a":1,"b":2}}'[:-1],
    ]
    for payload in payloads:
        with pytest.raises(CapabilityTaskError):
            execute_capability_json(payload)


def test_direct_api_rejects_unbounded_tasks_and_unknown_operation():
    with pytest.raises(CapabilityTaskError, match="bounded"):
        execute_capability_task({
            "operation": "content.sha256", "args": {"text": "A" * MAX_INPUT_BYTES},
        })
    with pytest.raises(CapabilityTaskError):
        execute_capability_task({"operation": "shell", "args": {}})
    with pytest.raises(CapabilityTaskError):
        execute_capability_task({"operation": "math.add", "args": {"a": 1, "b": 2}, "extra": True})


def test_all_tasks_are_deterministic_and_have_output_bounds():
    inputs = [
        {"operation": "math.add", "args": {"a": 1, "b": 2}},
        {"operation": "grid.shortest_path", "args": {
            "start": {"x": 0, "y": 0}, "goal": {"x": 2, "y": 2},
            "width": 3, "height": 3, "blocked": [],
        }},
        {"operation": "evidence.lookup", "args": {"facts": {"note": "source"},
                                                  "key": "note"}},
    ]
    for task in inputs:
        first = execute_capability_task(task)
        second = execute_capability_task(task)
        assert first == second
        assert len(json.dumps(first).encode("utf-8")) <= MAX_OUTPUT_BYTES


def test_bound_random_grid_routes_do_not_revisit_cells():
    rng = random.Random(1199)
    for _ in range(60):
        w, h = 6, 5
        blockers = [{"x": x, "y": y}
                    for x in range(w) for y in range(h)
                    if (x, y) not in ((0, 0), (w - 1, h - 1))
                    and rng.random() < 0.25]
        route = run(
            "grid.shortest_path", start={"x": 0, "y": 0},
            goal={"x": w - 1, "y": h - 1}, width=w, height=h, blocked=blockers,
        )
        if route["reachable"]:
            vertices = [(x["x"], x["y"]) for x in route["path"]]
            assert len(vertices) == len(set(vertices))
            assert len(vertices) - 1 == route["steps"]
        else:
            assert route["steps"] is None and route["path"] == []


def test_frozen_console_and_unified_cli_expose_model_free_capabilities(
    tmp_path: Path, capsys,
):
    from skeleton.app.offline_cli import main as console
    from skeleton.app.cli import run_app_cli

    assert console(["--capability-list", "--json"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert len(catalog["operations"]) == 31
    assert catalog["training_examples_required"] == 0
    task = tmp_path / "task.json"
    task.write_text(json.dumps({
        "operation": "game.damage",
        "args": {"health": 9, "damage": 3},
    }), encoding="utf-8")
    assert console(["--capability-file", str(task), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == 6
    assert run_app_cli([
        "local-ai", "--capability-file", str(task), "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == 6


def test_capability_cli_rejects_model_or_mutating_state_modes(
    tmp_path: Path, capsys,
):
    from skeleton.app.offline_cli import main as console
    task = tmp_path / "task.json"
    task.write_text('{"operation":"math.add","args":{"a":1,"b":2}}', encoding="utf-8")
    assert console(["--capability-file", str(task), "--model", "weights.json"]) == 2
    assert console(["--capability-list", "--snapshot-to", str(tmp_path / "data")]) == 2
    assert console(["--capability-file", str(task), "--queue-status"]) == 2
    assert console(["--capability-list", "--qualify-model"]) == 2
    assert capsys.readouterr().out == ""


def test_capability_cli_rejects_symlink_and_missing_input_without_side_effects(
    tmp_path: Path, capsys,
):
    from skeleton.app.offline_cli import main as console
    outside = tmp_path / "outside.json"
    outside.write_text('{"operation":"game.damage","args":{"health":3,"damage":1}}')
    link = tmp_path / "alias.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unsupported")
    assert console(["--capability-file", str(link), "--json"]) == 1
    assert console(["--capability-file", str(tmp_path / "absent.json")]) == 1
    assert capsys.readouterr().out == ""


def test_pathfinding_long_output_fails_closed_within_budget():
    # 1x32 map remains within the output budget; all returned steps are finite.
    result = run(
        "grid.shortest_path", start={"x": 0, "y": 0},
        goal={"x": 0, "y": 31}, width=1, height=32, blocked=[],
    )
    assert result["steps"] == 31
    assert len(result["path"]) == 32
