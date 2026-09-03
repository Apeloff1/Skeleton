"""Forge repair scaffold tests."""
from __future__ import annotations

from skeleton.forge.repair import attempt_repair, candidate_failures, latest_repair_plan
from skeleton.organism.quality_state import append_quality


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


def test_attempt_repair_patches_missing_extends_and_func():
    files = {
        "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
        "scenes/levels/run_level.tscn": '[gd_scene load_steps=1 format=3]\n[node name="RunLevel" type="Node2D"]\n',
        "scripts/world/world_map.gd": 'var x = 1\n',
    }
    out = attempt_repair(files, request="repair world map")
    assert out["changed"] == 1
    assert out["actions"]
    assert "extends Node" in out["files"]["scripts/world/world_map.gd"]


def test_attempt_repair_comments_eval_once():
    files = {
        "project.godot": 'config_version=5\n',
        "scripts/world/world_map.gd": 'extends Node\nfunc tick():\n    eval(user_input)\n',
    }
    out = attempt_repair(files, request="repair world map")
    assert out["changed"] == 1
    assert "# eval(" in out["files"]["scripts/world/world_map.gd"]
