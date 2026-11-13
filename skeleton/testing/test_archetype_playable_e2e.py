"""E2E: every forge archetype ships a playable scene, controller and core loop.

Static gates always run. When a Godot 4.3 binary is available the forged
project is imported and each archetype scene is booted headless on autopilot;
the core loop must report completion inside its frame budget.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from skeleton.context.pipeline import GameForgeRun
from skeleton.forge.archetype_content import (
    COMPLETE_MARKER,
    FAILED_MARKER,
    archetype_files,
    attach_archetype_content,
    content_archetypes,
)
from skeleton.forge.archetypes import default_library
from skeleton.forge.gdscript_check import check_files
from skeleton.forge.projector import write_project


def _godot() -> str | None:
    for env in ("SKELETON_GODOT_BIN", "GODOT_BINARY"):
        value = os.environ.get(env)
        if value and Path(value).is_file():
            return value
    return shutil.which("godot4") or shutil.which("godot")


def test_every_library_archetype_has_playable_content():
    assert set(default_library().names()) <= set(content_archetypes())


@pytest.mark.parametrize("name", content_archetypes())
def test_archetype_files_are_complete(name):
    files = archetype_files(name)
    scene = files[f"scenes/archetypes/{name}/main.tscn"]
    controller = files[f"scripts/archetypes/{name}/player_controller.gd"]
    loop = files[f"scripts/archetypes/{name}/core_loop.gd"]
    assert f"res://scripts/archetypes/{name}/core_loop.gd" in scene
    assert 'type="CharacterBody2D"' in scene
    assert "extends CharacterBody2D" in controller and "move_and_slide()" in controller
    assert 'Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")' in controller
    assert "func _tick(" in loop and COMPLETE_MARKER in loop and FAILED_MARKER in loop
    assert "{{" not in loop and "}}" not in loop
    # Actual non-headless gameplay must show objectives, controls and player
    # movement, not an invisible script declaring a completed win marker.
    assert "func _draw() -> void:" in loop
    assert "func _draw_objectives() -> void:" in loop
    assert "func _hud_status() -> String:" in loop
    assert "draw_circle(player.global_position" in loop
    assert "queue_redraw()" in loop
    assert "ForgeGameplayHUD" in loop and "TouchControls" in loop
    assert "Control.PRESET_BOTTOM_LEFT" in loop
    assert "Input.action_press(action)" in loop
    assert "Input.action_release(action)" in loop
    assert "_press_action.bind(action)" in loop
    assert "_release_action.bind(action)" in loop
    assert 'controls.mouse_filter = Control.MOUSE_FILTER_IGNORE' in loop
    assert "TextServer.AUTOWRAP_WORD_SMART" in loop
    assert 'DisplayServer.get_name() == "headless"' in loop
    assert "Completed:" not in loop  # explicit outcome is uppercase
    assert "COMPLETED: " in loop and "FAILED: " in loop


@pytest.mark.parametrize("name", content_archetypes())
def test_pipeline_attaches_playable_slice(name):
    out = GameForgeRun().execute("neon raid through a collapsing arcology", archetype=name, playable_content=True)
    assert out["succeeded"] is True
    assert out["forge"]["playable_archetype"] == name
    files = out["files"]
    assert f"scenes/archetypes/{name}/main.tscn" in files
    assert check_files(files) == []
    from skeleton.forge.playable_portal import verify_playable_portal
    assert verify_playable_portal(files, name)
    assert out["playable_portal"]["return_supported"] is True
    assert out["playable_portal"]["sealed"] is True


def test_attach_is_additive_and_falls_back():
    base = {"project.godot": "keep", f"scripts/archetypes/extraction/core_loop.gd": "custom"}
    with pytest.raises(ValueError, match="collides"):
        attach_archetype_content(base, "vision")
    merged = attach_archetype_content({"project.godot":"keep"}, "vision")
    assert merged["project.godot"] == "keep"
    assert "scenes/archetypes/extraction/main.tscn" in merged


@pytest.mark.skipif(_godot() is None, reason="Godot 4.3 binary not installed")
@pytest.mark.parametrize("name", content_archetypes())
def test_core_loop_completes_in_real_godot(name, tmp_path):
    godot = _godot()
    out = GameForgeRun().execute("neon raid", archetype=name, playable_content=True)
    write_project(tmp_path, out["files"], overwrite=True)
    env = dict(os.environ, GODOT_SILENCE_ROOT_WARNING="1")
    subprocess.run([godot, "--headless", "--editor", "--quit", "--path", str(tmp_path)],
                   capture_output=True, timeout=180, check=False, env=env)
    proc = subprocess.run(
        [godot, "--headless", "--fixed-fps", "60", "--quit-after", "6000", "--path", str(tmp_path),
         f"res://scenes/archetypes/{name}/main.tscn"],
        capture_output=True, text=True, timeout=180, check=False, env=env,
    )
    log = proc.stdout + proc.stderr
    assert "SCRIPT ERROR" not in log, log[-2000:]
    assert f"{COMPLETE_MARKER} {name}" in log, log[-2000:]
    assert proc.returncode == 0
