"""Forge repair scaffold tests."""
from __future__ import annotations

from skeleton.forge.repair import candidate_failures, latest_repair_plan
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
