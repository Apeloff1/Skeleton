"""Focused acceptance tests for the real Godot scene smoke command boundary."""
from pathlib import Path

import pytest

from skeleton.godot_export.runner import GodotRunner, RunResult


def test_scene_smoke_invokes_engine_with_bounded_frame_count(tmp_path: Path) -> None:
    calls = []

    def execute(argv, cwd, timeout):
        calls.append((tuple(argv), cwd, timeout))
        return RunResult(0, "engine started and exited", tuple(argv))

    runner = GodotRunner("godot", exec_fn=execute)
    result = runner.play_scene(tmp_path, "res://scenes/first_playable.tscn", frames=180)
    assert result.ok
    assert calls == [(
        ("godot", "--headless", "--path", str(tmp_path), "--quit-after", "180",
         "res://scenes/first_playable.tscn"),
        tmp_path, 90,
    )]


@pytest.mark.parametrize("scene", [
    "", "scenes/start.tscn", "res://", "res://../outside.tscn",
    "res://scenes//start.tscn", "res://scenes/./start.tscn",
    "res://scenes/../../start.tscn", "res://scenes\\start.tscn",
    "res://scenes/start.gd", "res://scenes/start\n.tscn",
])
def test_scene_smoke_rejects_invalid_resource_paths(tmp_path: Path, scene: str) -> None:
    runner = GodotRunner("godot", exec_fn=lambda *_: pytest.fail("must not execute"))
    with pytest.raises(ValueError):
        runner.play_scene(tmp_path, scene)


@pytest.mark.parametrize("frames", [True, 0, -1, 36001, 1.5, None])
def test_scene_smoke_rejects_invalid_frame_budget(tmp_path: Path, frames) -> None:
    runner = GodotRunner("godot", exec_fn=lambda *_: pytest.fail("must not execute"))
    with pytest.raises(ValueError):
        runner.play_scene(tmp_path, "res://start.tscn", frames=frames)


@pytest.mark.parametrize("timeout", [True, 0, -1, 3601, 1.5, None])
def test_scene_smoke_rejects_invalid_timeout(tmp_path: Path, timeout) -> None:
    runner = GodotRunner("godot", exec_fn=lambda *_: pytest.fail("must not execute"))
    with pytest.raises(ValueError):
        runner.play_scene(tmp_path, "res://start.tscn", timeout=timeout)


def test_scene_smoke_preserves_native_failure(tmp_path: Path) -> None:
    runner = GodotRunner("godot", exec_fn=lambda argv, cwd, timeout: RunResult(127, "missing binary", tuple(argv)))
    result = runner.play_scene(tmp_path, "res://start.tscn")
    assert result.launch_failed and not result.ok
