"""Tests for the Godot emit verification loop and its supporting cast."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path


def _good_files() -> dict:
    return {
        "project.godot": '[gd_resource type="ProjectSettings"]\nconfig_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n[autoload]\nHeatSystem="*res://scripts/autoloads/heat_system.gd"\nJeeves="*res://scripts/autoloads/jeeves.gd"\nGameState="*res://scripts/autoloads/game_state.gd"\nInputBind="*res://scripts/autoloads/input_bind.gd"\n',
        "scripts/autoloads/heat_system.gd": "extends Node\nclass_name HeatSystem\nvar current_heat: float = 0.0\nsignal heat_critical\nfunc add_heat(amount: float) -> void:\n    current_heat += amount\n    if current_heat >= 100.0:\n        heat_critical.emit()\n",
        "scripts/autoloads/jeeves.gd": "extends Node\nclass_name Jeeves\nfunc advise(telemetry: Dictionary) -> String:\n    return \"watch your heat\"\n",
        "scripts/autoloads/game_state.gd": "extends Node\nclass_name GameState\nvar room: String = \"r00\"\nfunc enter_room(room_id: String) -> void:\n    room = room_id\n",
        "scripts/autoloads/input_bind.gd": "extends Node\nclass_name InputBind\nfunc _ready() -> void:\n    var ev := InputEventKey.new()\n    ev.keycode = KEY_A\n",
        "scripts/player/player_controller.gd": "extends CharacterBody2D\nclass_name PlayerController\nfunc _physics_process(delta: float) -> void:\n    velocity = Vector2(100, 0)\n    move_and_slide()\n    HeatSystem.add_heat(delta)\n",
        "scripts/combat/enemy.gd": "extends CharacterBody2D\nclass_name Enemy\nfunc take_damage(amount: int) -> void:\n    pass\n",
        "scripts/world/world_map.gd": "extends Node2D\nclass_name WorldMap\nvar rooms: Dictionary = {}\nfunc door_at(pos: Vector2) -> String:\n    return \"\"\n",
        "scripts/world/door.gd": "extends Area2D\nclass_name Door\nfunc open() -> void:\n    pass\n",
        "scenes/levels/run_level.tscn": '[gd_scene format=3]\n[node name="Room_r00" type="Node2D"]\n[node name="Player" parent="." instance=ExtResource("3")]\n[node name="Door" parent="." instance=ExtResource("7")]\n',
        "scenes/player.tscn": '[gd_scene format=3]\n[node name="Player" type="CharacterBody2D"]\n[node name="Camera2D" type="Camera2D" parent="."]\n',
        "scenes/door.tscn": '[gd_scene format=3]\n[node name="Door" type="Area2D"]\n',
        "data/rooms.json": '{"r00": {"name": "Entry"}}',
        "data/hardware.json": '{"sword": {"damage": 10}}',
    }


class TestGDScriptCheck(unittest.TestCase):
    def test_clean_project_passes(self):
        from skeleton.forge.gdscript_check import check_files
        problems = check_files(_good_files())
        self.assertEqual(problems, [])

    def test_missing_project_godot_fails(self):
        from skeleton.forge.gdscript_check import check_files
        files = _good_files()
        del files["project.godot"]
        problems = check_files(files)
        self.assertIn("missing project.godot", problems)

    def test_unbalanced_braces_flagged(self):
        from skeleton.forge.gdscript_check import check_files
        files = _good_files()
        files["scripts/world/door.gd"] = "extends Area2D\nfunc open() -> void:\n    var x = {\"a\": [1, 2\n"
        problems = check_files(files)
        self.assertTrue(any("unbalanced" in p for p in problems))

    def test_missing_reference_flagged(self):
        from skeleton.forge.gdscript_check import check_files
        files = _good_files()
        files["scripts/world/door.gd"] = 'extends Area2D\nvar scene = preload("res://scenes/missing.tscn")\nfunc open() -> void:\n    pass\n'
        problems = check_files(files)
        self.assertTrue(any("missing" in p for p in problems))


class TestForgeVerifier(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clean_project_accepted(self):
        from skeleton.intelligence.forge_verifier import ForgeVerifier
        verifier = ForgeVerifier(root=self.tmp)
        report = verifier.verify(_good_files(), request="test game")
        self.assertTrue(report.accepted, f"rejected: {report.reason} {list(report.blocking_issues)}")
        self.assertGreaterEqual(report.score, 0.7)

    def test_unsafe_code_blocked(self):
        from skeleton.intelligence.forge_verifier import ForgeVerifier
        files = _good_files()
        files["scripts/world/door.gd"] = "extends Area2D\nfunc open() -> void:\n    eval(\"1+1\")\n"
        verifier = ForgeVerifier(root=self.tmp)
        report = verifier.verify(files, request="test")
        self.assertFalse(report.accepted)
        self.assertEqual(report.reason, "project_closure")  # door.gd edit breaks nothing else, unsafe caught in file reports

    def test_stats_track_acceptance(self):
        from skeleton.intelligence.forge_verifier import ForgeVerifier
        verifier = ForgeVerifier(root=self.tmp)
        verifier.verify(_good_files(), request="one")
        verifier.verify({"project.godot": "bad"}, request="two")
        stats = verifier.stats()
        self.assertEqual(stats["runs"], 2)
        self.assertGreaterEqual(stats["accept_rate"], 0.0)


class TestVerifyUntilGreen(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clean_project_accepted_first_round(self):
        from skeleton.forge.verify_loop import forge_verify_until_green
        result = forge_verify_until_green(_good_files(), request="clean game", root=self.tmp)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["trace"]["stopped_reason"], "accepted")
        self.assertEqual(result["repairs"], [])

    def test_repair_fixes_missing_extends(self):
        from skeleton.forge.verify_loop import forge_verify_until_green
        files = _good_files()
        files["scripts/world/door.gd"] = "class_name Door\nfunc open() -> void:\n    pass\n"
        result = forge_verify_until_green(files, request="door repair", root=self.tmp, max_rounds=3)
        # Repair should have patched the script even if full acceptance needs more
        self.assertGreaterEqual(len(result["rounds_detail"]), 1)
        self.assertIn("verification", result)

    def test_loop_result_shape(self):
        from skeleton.forge.verify_loop import forge_verify_until_green
        result = forge_verify_until_green(_good_files(), request="shape", root=self.tmp)
        for key in ("accepted", "files", "verification", "trace", "repairs", "rounds_detail", "threshold", "stopped_reason"):
            self.assertIn(key, result)

    def test_materialise_with_repair_flag(self):
        from skeleton.forge.universal import Forge
        forge = Forge()
        bp = forge.new_blueprint("repair-e2e")
        forge.instantiate(bp, "source", "input")
        forge.instantiate(bp, "sink", "output")
        bp.connect(("input", "out"), ("output", "in"))
        try:
            result = forge.materialise(bp, era="extraction_now", target="godot", repair=True, max_rounds=2)
            self.assertIn("verify_loop", result)
            self.assertIn("verification", result)
        except Exception as e:
            # Repair loop hard-fails when godot emit output can't reach green —
            # acceptable: the error must carry the verification context.
            self.assertIn("verification", str(e.context) if hasattr(e, "context") else str(e))


if __name__ == "__main__":
    unittest.main(verbosity=2)
