"""Forge repair scaffold tests."""
from __future__ import annotations

from skeleton.forge.repair import attempt_repair, candidate_failures, latest_repair_plan
from skeleton.organism.quality_state import append_quality, latest_repair


def test_latest_repair_plan_returns_no_failure(tmp_path):
    card = latest_repair_plan(root=tmp_path)
    assert card["ok"] == 0
    assert card["reason"] == "no-failure"


def test_latest_repair_plan_targets_latest_failure(tmp_path):
    append_quality({"surface": "forge", "accepted": False, "reason": "low_score", "score": 0.2, "weakest_path": "scripts/world_map.gd", "summary": {"blocking_issues": 1}}, root=tmp_path)
    card = latest_repair_plan(root=tmp_path)
    assert card["ok"] == 1
    assert card["surface"] == "forge"
    assert card["targets"]


def test_candidate_failures_reads_recent_forge_failures(tmp_path):
    append_quality({"surface": "forge", "accepted": False, "reason": "low_score", "score": 0.2, "weakest_path": "a.gd"}, root=tmp_path)
    append_quality({"surface": "forge", "accepted": False, "reason": "project_closure", "score": 0.1, "weakest_path": "project.godot"}, root=tmp_path)
    out = candidate_failures(root=tmp_path, limit=2)
    assert out["n"] == 2
    assert out["items"]


def test_attempt_repair_patches_missing_extends_and_func(tmp_path):
    files = {
        "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
        "scenes/levels/run_level.tscn": '[gd_scene load_steps=1 format=3]\n[node name="RunLevel" type="Node2D"]\n',
        "scripts/world/world_map.gd": 'var x = 1\n',
    }
    out = attempt_repair(files, request="repair world map", root=tmp_path)
    assert out["changed"] == 1
    assert out["actions"]
    assert "extends Node" in out["files"]["scripts/world/world_map.gd"]
    assert latest_repair(root=tmp_path, surface="forge")["kind"] == "repair"


def test_attempt_repair_comments_eval_once(tmp_path):
    files = {
        "project.godot": 'config_version=5\n',
        "scripts/world/world_map.gd": 'extends Node\nfunc tick():\n    eval(user_input)\n',
    }
    out = attempt_repair(files, request="repair world map", root=tmp_path)
    assert out["changed"] == 1
    assert "# eval(" in out["files"]["scripts/world/world_map.gd"]


def test_attempt_repair_restores_eventbus_autoload(tmp_path):
    files = {
        "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
        "scenes/levels/run_level.tscn": '[gd_scene load_steps=1 format=3]\n[node name="RunLevel" type="Node2D"]\n',
    }
    out = attempt_repair(files, request="repair project", root=tmp_path)
    assert out["changed"] == 1
    assert 'EventBus="*res://scripts/autoloads/event_bus.gd"' in out["files"]["project.godot"]


def test_attempt_repair_prefers_evidence_target(tmp_path):
    files = {
        "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
        "scenes/levels/run_level.tscn": '[gd_scene load_steps=1 format=3]\n[node name="RunLevel" type="Node2D"]\n',
        "scripts/world/world_map.gd": 'var x = 1\n',
        "scripts/autoloads/heat_system.gd": 'func bad():\n    eval(user_input)\n',
    }
    out = attempt_repair(files, request="repair project", root=tmp_path, evidence={
        "top_file_reports": [{"path": "scripts/autoloads/heat_system.gd", "hard_issues": ["unsafe constructs detected"]}]
    })
    assert out["targeted_path"].endswith("heat_system.gd")


def test_attempt_repair_restores_run_level_and_player_ref(tmp_path):
    files = {
        "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
    }
    out = attempt_repair(files, request="repair project", root=tmp_path)
    assert "scenes/levels/run_level.tscn" in out["files"]


def test_attempt_repair_restores_door_scene_and_ref(tmp_path):
    files = {
        "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
        "scenes/levels/run_level.tscn": '[gd_scene load_steps=1 format=3]\n[node name="RunLevel" type="Node2D"]\n[node name="Room_r00" type="Node2D" parent="."]\n',
    }
    out = attempt_repair(files, request="repair project", root=tmp_path)
    assert "scenes/door.tscn" in out["files"]
    assert 'instance=ExtResource("7")' in out["files"]["scenes/levels/run_level.tscn"]


def test_materialise_can_repair_once_and_return_result(tmp_path, monkeypatch):
    from skeleton.forge.universal import Forge

    forge = Forge(root=tmp_path)
    bp = forge.new_blueprint("Repairable")
    forge.instantiate(bp, "player", "player")

    def weak_emit(*args, **kwargs):
        return {
            "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
            "scenes/levels/run_level.tscn": '[gd_scene load_steps=1 format=3]\n[node name="RunLevel" type="Node2D"]\n',
            "scripts/world/world_map.gd": 'var x = 1\n',
        }

    monkeypatch.setattr("skeleton.forge.godot_emit.emit_godot", weak_emit)
    out = forge.materialise(bp, target="godot", repair=True)
    assert "repair" in out
    assert out["repair"]["changed"] == 1
