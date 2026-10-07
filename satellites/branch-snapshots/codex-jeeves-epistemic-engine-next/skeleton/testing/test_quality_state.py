"""Quality state persistence tests."""
from __future__ import annotations

from skeleton.organism.quality_state import append_quality, append_repair, latest_failure, latest_quality, latest_repair, load_quality, quality_snapshot, recent_activity, repair_candidates


def test_quality_state_appends_and_reads(tmp_path):
    append_quality({"surface": "plan", "accepted": True, "reason": "accepted", "score": 0.9, "weakest_path": "grounding"}, root=tmp_path)
    append_quality({"surface": "npc", "accepted": False, "reason": "low_score", "score": 0.3, "weakest_path": "behavior"}, root=tmp_path)
    rows = load_quality(root=tmp_path)
    assert len(rows) == 2
    assert latest_quality(root=tmp_path)["surface"] == "npc"
    snap = quality_snapshot(root=tmp_path)
    assert snap["rollup"]["count"] == 2
    assert snap["rollup"]["rejected"] == 1
    assert snap["latest_failure"]["surface"] == "npc"


def test_latest_failure_and_repair_candidates(tmp_path):
    append_quality({"surface": "forge", "accepted": False, "reason": "low_score", "score": 0.2, "weakest_path": "scripts/world_map.gd", "summary": {"blocking_issues": 1}}, root=tmp_path)
    append_quality({"surface": "forge", "accepted": False, "reason": "project_closure", "score": 0.1, "weakest_path": "project.godot", "summary": {"blocking_issues": 2}}, root=tmp_path)
    fail = latest_failure(root=tmp_path, surface="forge")
    assert fail["reason"] == "project_closure"
    candidates = repair_candidates(root=tmp_path, surface="forge")
    assert len(candidates) == 2


def test_repair_entries_are_separate_from_failures(tmp_path):
    append_quality({"surface": "forge", "accepted": False, "reason": "low_score", "score": 0.2, "weakest_path": "a.gd"}, root=tmp_path)
    append_repair({"surface": "forge", "ok": 1, "before": {"reason": "low_score"}, "after": {"reason": "accepted", "score": 0.9, "weakest_path": "a.gd"}, "actions": [{"path": "a.gd"}]}, root=tmp_path)
    assert latest_failure(root=tmp_path, surface="forge")["reason"] == "low_score"
    assert latest_repair(root=tmp_path, surface="forge")["kind"] == "repair"


def test_quality_evidence_is_persisted(tmp_path):
    append_quality({
        "surface": "forge",
        "accepted": False,
        "reason": "unsafe_code",
        "score": 0.1,
        "weakest_path": "scripts/world/world_map.gd",
        "evidence": {"top_file_reports": [{"path": "scripts/world/world_map.gd", "hard_issues": ["unsafe constructs detected"]}], "issue_names": ["unsafe constructs detected"], "top_paths": ["scripts/world/world_map.gd"]},
    }, root=tmp_path)
    row = latest_failure(root=tmp_path, surface="forge")
    assert row["evidence"]["top_file_reports"][0]["path"].endswith("world_map.gd")


def test_recent_activity_rollup(tmp_path):
    append_quality({"surface": "plan", "accepted": True, "reason": "accepted", "score": 0.9}, root=tmp_path)
    append_repair({"surface": "forge", "ok": 1, "before": {"reason": "low_score"}, "after": {"reason": "accepted", "score": 0.8}}, root=tmp_path)
    activity = recent_activity(root=tmp_path)
    assert activity["n"] == 2
    assert activity["items"]


def test_repair_rollup_tracks_top_target(tmp_path):
    append_repair({"surface": "forge", "ok": 1, "before": {"reason": "low_score"}, "after": {"reason": "accepted", "score": 0.8, "weakest_path": "a.gd"}, "targeted_path": "a.gd"}, root=tmp_path)
    append_repair({"surface": "forge", "ok": 0, "before": {"reason": "unsafe_code"}, "after": {"reason": "low_score", "score": 0.4, "weakest_path": "a.gd"}, "targeted_path": "a.gd"}, root=tmp_path)
    snap = quality_snapshot(root=tmp_path)
    assert snap["repairs"]["top_target"] == "a.gd"


def test_failure_rollup_tracks_top_issue(tmp_path):
    append_quality({"surface": "forge", "accepted": False, "reason": "unsafe_code", "score": 0.1, "evidence": {"issue_names": ["unsafe constructs detected"]}}, root=tmp_path)
    append_quality({"surface": "npc", "accepted": False, "reason": "low_score", "score": 0.2, "evidence": {"issue_names": ["unsafe constructs detected", "missing traits"]}}, root=tmp_path)
    snap = quality_snapshot(root=tmp_path)
    assert snap["failures"]["top_issue"] == "unsafe constructs detected"
