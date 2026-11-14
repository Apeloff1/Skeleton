"""Live Forge game acceptance, distinct from the static CoreLoop startup proof.

Native cases run the actual installed Godot and the emitted input replay. Set
SKELETON_GAME_BUILDER_REQUIRE_GODOT=1 in a native CI job to make absence fail.
These cases do not establish framebuffer, device-controller or release quality.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from skeleton.forge.game_builder import build_playable_game
from skeleton.forge.game_design_spec import GOLDEN_BRIEFS, compile_brief
from skeleton.forge.gdscript_check import check_files
from skeleton.forge.genre_project import CORE_LOOP_GD, attach_genre
from skeleton.forge.playable_runtime import (
    INTERACTIVE_SCHEMA, RUNTIME_PATH, SCENE_PATH, SMOKE_PATH,
    attach_playable, runtime_manifest,
)
from skeleton.forge.playtest import scan_log


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("forge-interactive")
    results = {}
    for item in GOLDEN_BRIEFS:
        destination = root / item["genre"]
        result = build_playable_game(item["brief"], playtest_mode="off", out=str(destination))
        assert result["ok"] is True, result.get("error") or result.get("check")
        results[item["genre"]] = (result, destination)
    return results


@pytest.fixture(scope="module")
def godot():
    selected = os.environ.get("SKELETON_GODOT_BIN") or shutil.which("godot4") or shutil.which("godot")
    required = os.environ.get("SKELETON_GAME_BUILDER_REQUIRE_GODOT") == "1"
    if not selected or not Path(selected).is_file():
        if required:
            pytest.fail("native Forge acceptance requires an installed Godot 4 binary")
        pytest.skip("native Godot not installed; interactive source is not qualified by this skip")
    version = subprocess.run([selected, "--version"], capture_output=True, text=True, timeout=10, check=False)
    assert version.returncode == 0 and version.stdout.strip().startswith("4."), version.stdout + version.stderr
    return selected


def engine(binary: str, project: Path, *arguments: str) -> str:
    completed = subprocess.run(
        [binary, "--headless", "--path", str(project), *arguments],
        capture_output=True, text=True, timeout=90, check=False,
        env={**os.environ, "GODOT_SILENCE_ROOT_WARNING": "1"},
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output[-14000:]
    assert not scan_log(output), output[-14000:]
    return output


@pytest.mark.parametrize("genre", ["top_down_shooter", "platformer", "rpg_roguelike"])
def test_generated_main_scene_is_live_and_preserves_existing_content_proof(built, genre):
    result, destination = built[genre]
    files = result["files"]
    assert not check_files(files)
    assert f'run/main_scene="res://{SCENE_PATH}"' in files["project.godot"]
    assert files["scripts/autoloads/core_loop.gd"] == CORE_LOOP_GD
    assert RUNTIME_PATH in files and SMOKE_PATH in files
    manifest = json.loads(files["data/interactive_runtime.json"])
    assert manifest["schema"] == INTERACTIVE_SCHEMA
    assert manifest["genre"] == genre
    assert manifest["external_assets"] is False
    assert "input_journey_verified" not in manifest
    assert json.loads(files["data/design_spec.json"]) == result["spec"]
    assert (destination / SCENE_PATH).is_file()
    # Reattachment is deterministic and preserves one main scene and the
    # exact original spec identity; a repair never creates a parallel project.
    assert attach_genre(files, result["spec"], result["content"]) == files


def test_runtime_manifest_consumes_only_closed_validated_gameplay_data():
    spec = compile_brief("A small platformer. Theme: frost. Difficulty: hard. Player speed: 300.")
    manifest = runtime_manifest(spec)
    assert manifest["gameplay"]["theme"] == "frost"
    assert manifest["gameplay"]["difficulty"] == "hard"
    assert manifest["gameplay"]["player_speed"] == 300
    for invalid in ({**manifest["gameplay"], "player_speed": True},
                    {**manifest["gameplay"], "theme": "load external code"},
                    {**manifest["gameplay"], "script": "res://foreign.gd"}):
        with pytest.raises(ValueError):
            runtime_manifest({**spec, "gameplay": invalid})
    legacy = dict(spec)
    legacy.pop("gameplay", None)
    assert runtime_manifest(legacy)["gameplay"]["player_speed"] == 230


def test_live_attachment_rejects_unknown_genre_and_missing_main_scene():
    spec = compile_brief("A small top-down shooter")
    with pytest.raises(ValueError):
        runtime_manifest({**spec, "genre": "remote-script"})
    with pytest.raises(ValueError):
        attach_playable({"project.godot": "config_version=5\n"}, spec)


@pytest.mark.parametrize("genre", ["top_down_shooter", "platformer", "rpg_roguelike"])
def test_real_godot_input_playthrough_wins_pauses_and_restarts(built, godot, genre):
    _, destination = built[genre]
    engine(godot, destination, "--import")
    output = engine(godot, destination, "--fixed-fps", "60", "--script", "res://" + SMOKE_PATH)
    lines = [line.split("FORGE_INTERACTIVE_OK ", 1)[1] for line in output.splitlines()
             if line.startswith("FORGE_INTERACTIVE_OK ")]
    assert len(lines) == 1, output
    receipt = json.loads(lines[0])
    assert receipt["genre"] == genre and receipt["phase"] == "won"
    assert receipt["input_frames"] >= 20 and receipt["movement_distance"] > 100
    assert receipt["pause_verified"] is True and receipt["restart_verified"] is True
    if genre == "platformer":
        assert receipt["jumps"] > 0 and receipt["collected"] >= 5
    else:
        assert receipt["shots"] > 0 and receipt["defeated"] >= 3


@pytest.mark.parametrize("genre", ["top_down_shooter", "platformer", "rpg_roguelike"])
def test_real_godot_boot_never_autocompletes_the_live_game(built, godot, genre):
    _, destination = built[genre]
    output = engine(godot, destination, "--fixed-fps", "60", "--quit-after", "60")
    assert "CORE_LOOP_OK genre=" + genre in output
    assert "FORGE_INTERACTIVE_OK" not in output
    assert "FORGE_GAMEPLAY_RESULT" not in output


def test_real_platformer_missing_jumps_loses_and_restart_recovers(built, godot):
    _, destination = built["platformer"]
    script = destination / "scripts/runtime/loss_acceptance.gd"
    script.write_text('''extends SceneTree
func _initialize() -> void:
    call_deferred("_run")
func _run() -> void:
    change_scene_to_file("res://scenes/gameplay.tscn")
    await process_frame
    await physics_frame
    var game: Node2D = current_scene
    Input.action_press("forge_right")
    for frame: int in range(3600):
        await physics_frame
        if str(game.phase) == "lost":
            break
    Input.action_release("forge_right")
    if str(game.phase) != "lost" or float(game.hp) > 0.0:
        push_error("ordinary movement without jumps did not lose")
        quit(1)
        return
    Input.action_press("forge_restart")
    await physics_frame
    Input.action_release("forge_restart")
    await physics_frame
    if str(game.phase) != "playing" or float(game.hp) != 100.0:
        push_error("restart did not recover from a genuine loss")
        quit(1)
        return
    print("FORGE_LOSS_RESTART_OK")
    quit(0)
''')
    output = engine(godot, destination, "--fixed-fps", "60", "--script", "res://scripts/runtime/loss_acceptance.gd")
    assert "FORGE_GAMEPLAY_RESULT genre=platformer outcome=lost" in output
    assert "FORGE_LOSS_RESTART_OK" in output
