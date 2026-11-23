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
    INTERACTIVE_SCHEMA, PROFILE_COUNTERS, RUNTIME_PATH, SAVE_PATH, SAVE_SCHEMA, SCENE_PATH, SMOKE_PATH,
    attach_playable, runtime_manifest, save_profile_canonical, save_profile_digest, save_profile_id,
    verify_save_document,
)
from skeleton.forge.playtest import scan_log


LIVE_GENRES = ["top_down_shooter", "platformer", "rpg_roguelike", "puzzle"]


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
        # user:// lives under XDG_DATA_HOME; keep saves inside the test's tmp tree.
        env={**os.environ, "GODOT_SILENCE_ROOT_WARNING": "1",
             "XDG_DATA_HOME": str(project.parent / f"{project.name}-userdata")},
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output[-14000:]
    assert not scan_log(output), output[-14000:]
    return output


@pytest.mark.parametrize("genre", LIVE_GENRES)
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


@pytest.mark.parametrize("genre", LIVE_GENRES)
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
    # Save/load: the file Godot wrote verifies under the independent Python oracle.
    assert receipt["save_verified"] is True and receipt["save_status"] == "loaded"
    save_file = Path(receipt["save_file"])
    assert save_file.is_relative_to(destination.parent)
    saved = json.loads(save_file.read_text(encoding="utf-8"))
    status, profile = verify_save_document(saved, built[genre][0]["spec"]["spec_id"])
    assert status == "loaded", saved
    assert profile == receipt["profile"]
    assert profile["runs"] == 1 and profile["wins"] == 1 and profile["losses"] == 0
    assert profile["best_score"] == receipt["score"] and profile["best_time_ms"] > 0
    if genre == "platformer":
        assert receipt["jumps"] > 0 and receipt["collected"] >= 5
    elif genre == "puzzle":
        result, _ = built[genre]
        assert receipt["mistakes"] == 0 and receipt["puzzle_solved"] is True
        assert receipt["activations"] == result["content"]["puzzle"]["moves"]
        assert receipt["room"] == len(result["content"]["puzzle"]["rooms"])
    else:
        assert receipt["shots"] > 0 and receipt["defeated"] >= 3


@pytest.mark.parametrize("genre", LIVE_GENRES)
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


_PUZZLE_ACCEPTANCE = '''extends SceneTree
## Wrong pads cost vitality and reset progress; repeated mistakes lose; restart recovers.
func _initialize() -> void:
    call_deferred("_run")

func _press(game: Node2D) -> void:
    Input.action_press("forge_interact")
    await physics_frame
    Input.action_release("forge_interact")
    await physics_frame

func _walk_to(game: Node2D, target: Vector2) -> void:
    for frame: int in range(600):
        var direction: Vector2 = target - Vector2(game.player)
        for action: String in ["forge_left", "forge_right", "forge_up", "forge_down"]:
            Input.action_release(action)
        if direction.length() < 12.0:
            break
        if direction.x > 8.0:
            Input.action_press("forge_right")
        elif direction.x < -8.0:
            Input.action_press("forge_left")
        if direction.y > 8.0:
            Input.action_press("forge_down")
        elif direction.y < -8.0:
            Input.action_press("forge_up")
        await physics_frame
    for action: String in ["forge_left", "forge_right", "forge_up", "forge_down"]:
        Input.action_release(action)
    for settle: int in range(10):
        await physics_frame

func _run() -> void:
    change_scene_to_file("res://scenes/gameplay.tscn")
    await process_frame
    await physics_frame
    var game: Node2D = current_scene
    var first: int = int(game.puzzle_order[0])
    var wrong: int = (first + 1) % game.pads.size()
    if game.puzzle_order.size() > 1 and int(game.puzzle_order[1]) == wrong:
        wrong = int(game.puzzle_order[1])
    await _walk_to(game, Vector2(game.pads[first]["pos"]))
    await _press(game)
    if int(game.puzzle_progress) != 1:
        push_error("correct pad did not advance the sequence")
        quit(1)
        return
    var decoy: int = -1
    for index: int in range(game.pads.size()):
        if index != int(game.puzzle_order[1]) and not bool(game.pads[index]["lit"]):
            decoy = index
            break
    await _walk_to(game, Vector2(game.pads[decoy]["pos"]))
    var before: float = float(game.hp)
    await _press(game)
    if int(game.puzzle_progress) != 0 or int(game.mistakes) != 1 or float(game.hp) >= before:
        push_error("wrong pad did not reset progress and cost vitality")
        quit(1)
        return
    for attempt: int in range(40):
        if str(game.phase) == "lost":
            break
        await _press(game)
    if str(game.phase) != "lost" or float(game.hp) > 0.0:
        push_error("repeated wrong pads did not lose")
        quit(1)
        return
    Input.action_press("forge_restart")
    await physics_frame
    Input.action_release("forge_restart")
    await physics_frame
    if str(game.phase) != "playing" or float(game.hp) != 100.0 or int(game.mistakes) != 0 or int(game.puzzle_progress) != 0:
        push_error("restart did not recover the puzzle from a genuine loss")
        quit(1)
        return
    print("FORGE_PUZZLE_ACCEPTANCE_OK")
    quit(0)
'''


def test_real_puzzle_wrong_pads_reset_cost_vitality_lose_and_restart(built, godot):
    _, destination = built["puzzle"]
    script = destination / "scripts/runtime/puzzle_acceptance.gd"
    script.write_text(_PUZZLE_ACCEPTANCE)
    engine(godot, destination, "--import")
    output = engine(godot, destination, "--fixed-fps", "60", "--script", "res://scripts/runtime/puzzle_acceptance.gd")
    assert "FORGE_GAMEPLAY_RESULT genre=puzzle outcome=lost" in output
    assert "FORGE_PUZZLE_ACCEPTANCE_OK" in output


def _profile(spec_id: str, **counters: int) -> dict:
    return {"spec_id": save_profile_id(spec_id), **{key: counters.get(key, 0) for key in PROFILE_COUNTERS}}


def _document(payload: dict) -> dict:
    return {"schema": SAVE_SCHEMA, "payload": payload, "checksum": save_profile_digest(payload)}


def test_save_oracle_accepts_valid_and_fails_closed_on_damage():
    spec = compile_brief("A small top-down shooter")
    payload = _profile(spec["spec_id"], runs=5, wins=2, losses=3, best_score=900, best_time_ms=61234)
    assert save_profile_canonical(payload).startswith(SAVE_SCHEMA + ";spec_id=")
    assert verify_save_document(_document(payload), spec["spec_id"]) == ("loaded", payload)
    tampered = _document(payload)
    tampered["payload"] = {**payload, "wins": 5}
    blank = _profile(spec["spec_id"])
    assert verify_save_document(tampered, spec["spec_id"]) == ("rejected", blank)
    inconsistent = _profile(spec["spec_id"], runs=1, wins=1, losses=1)
    assert verify_save_document(_document(inconsistent), spec["spec_id"])[0] == "rejected"
    for bad_value in (-1, 1.5, True, "3", None, 10**13):
        broken = {**payload, "runs": bad_value}
        assert verify_save_document({**_document(payload), "payload": broken}, spec["spec_id"])[0] == "rejected"
    assert verify_save_document({**_document(payload), "schema": "v0"}, spec["spec_id"])[0] == "rejected"
    assert verify_save_document("not a dict", spec["spec_id"])[0] == "rejected"
    other = _profile("another-game", runs=1, wins=1)
    assert verify_save_document(_document(other), spec["spec_id"]) == ("other_game", blank)


def test_runtime_manifest_declares_the_save_contract():
    for genre_brief in ("A small platformer", "A small puzzle game"):
        manifest = runtime_manifest(compile_brief(genre_brief))
        assert manifest["save"]["path"] == SAVE_PATH and manifest["save"]["schema"] == SAVE_SCHEMA
        assert manifest["save"]["fields"] == ["spec_id", *PROFILE_COUNTERS]
        assert "persistent progress save" in manifest["features"]


_SAVE_PROBE = '''extends SceneTree
## Boots the ordinary main scene (default save slot) and reports what it loaded.
func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    change_scene_to_file("res://scenes/gameplay.tscn")
    await process_frame
    await physics_frame
    var game: Node2D = current_scene
    print("FORGE_SAVE_PROBE " + JSON.stringify({"status": game.save_status, "profile": game.profile,
        "path": ProjectSettings.globalize_path(game.save_path)}))
    quit(0)
'''


def _probe(godot: str, destination: Path) -> dict:
    output = engine(godot, destination, "--fixed-fps", "60", "--script", "res://scripts/runtime/save_probe.gd")
    lines = [line.split("FORGE_SAVE_PROBE ", 1)[1] for line in output.splitlines()
             if line.startswith("FORGE_SAVE_PROBE ")]
    assert len(lines) == 1, output
    return json.loads(lines[0])


def test_real_godot_loads_python_written_saves_and_rejects_damage(built, godot):
    """Cross-process, cross-language save parity on the player's real save slot."""
    result, destination = built["top_down_shooter"]
    (destination / "scripts/runtime/save_probe.gd").write_text(_SAVE_PROBE)
    engine(godot, destination, "--import")
    first = _probe(godot, destination)
    save_file = Path(first["path"])
    assert save_file.name == "forge_save.json" and save_file.is_relative_to(destination.parent)
    if not save_file.exists():
        assert first["status"] == "fresh"
    spec_id = result["spec"]["spec_id"]
    payload = _profile(spec_id, runs=4, wins=3, losses=1, best_score=1234, best_time_ms=45678)
    save_file.parent.mkdir(parents=True, exist_ok=True)

    save_file.write_text(json.dumps(_document(payload)), encoding="utf-8")
    loaded = _probe(godot, destination)
    assert loaded["status"] == "loaded"
    assert {key: value if key == "spec_id" else int(value) for key, value in loaded["profile"].items()} == payload

    tampered = _document(payload)
    tampered["payload"]["best_score"] = 999999
    save_file.write_text(json.dumps(tampered), encoding="utf-8")
    rejected = _probe(godot, destination)
    assert rejected["status"] == "rejected" and int(rejected["profile"]["best_score"]) == 0

    save_file.write_text(json.dumps(_document(payload))[:40], encoding="utf-8")
    assert _probe(godot, destination)["status"] == "rejected"

    save_file.write_text(json.dumps(_document(_profile("someone-else", runs=1, wins=1))), encoding="utf-8")
    assert _probe(godot, destination)["status"] == "other_game"
    save_file.unlink()
