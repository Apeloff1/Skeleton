"""Actual persistent second/third-pass Jeeves boomerang queue coverage."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from skeleton.ai.training.jeeves_adaptive_sim_training import run_campaign
from skeleton.ai.training.jeeves_boomerang_queue import (
    create_queue, enqueue, advance_queue, verify_queue, retraining_review_drafts,
    main,
)
from skeleton.ai.training.jeeves_cinematic_simulation import CinematicSimError
from skeleton.testing.test_jeeves_cinematic_simulation import scene


def archived(tmp_path, *, source_id="chapter_one"):
    original = scene()
    original["scene_id"] = source_id
    source_file = tmp_path / (source_id + "-scene.json")
    archive_file = tmp_path / (source_id + "-campaign.json")
    source_file.write_text(json.dumps(original), encoding="utf-8")
    result = run_campaign(original, budget=4, seed=11)
    archive_file.write_text(json.dumps(result), encoding="utf-8")
    return source_file, archive_file, result


def test_enqueue_old_campaign_without_rerunning_it(tmp_path):
    src, archive, original = archived(tmp_path)
    q = create_queue(src, archive)
    assert q["generation"] == 0
    assert verify_queue(q, verify_sources=True)["pending_second_pass"] == 1
    assert q["entries"][0]["initial_case_count"] == 4
    assert q["entries"][0]["passes"] == []
    assert q["entries"][0]["source"]["archive_receipt_sha256"] == original["receipt_sha256"]
    assert not q["serving_weights_modified"] and q["optimizer_updates"] == 0


def test_boomerang_two_returns_find_controlled_differences(tmp_path):
    src, archive, original = archived(tmp_path)
    first = create_queue(src, archive)
    second = advance_queue(first, probes=4)
    verify_queue(second, verify_sources=True)
    assert second["generation"] == 1
    assert second["parent_queue_sha256"] == first["queue_sha256"]
    entry = second["entries"][0]
    assert entry["status"] == "awaiting_third_pass"
    assert entry["revisits_completed"] == 1
    a = entry["passes"][0]
    assert a["pass_number"] == 2 and a["scenarios_executed"] == 4
    assert a["original_simulation_reexecutions"] == 0
    assert a["forward_observations"] == a["reverse_observations"] == 4 * 28
    assert not set(row["scenario"]["scenario_id"] for row in a["results"]) & set(
        entry["initial_scenario_ids"])
    assert a["source_digest"] == original["source_digest"]
    assert a["actual_optimizer_updates"] == 0

    third = advance_queue(second, probes=4)
    verify_queue(third, verify_sources=True)
    done = third["entries"][0]
    assert done["status"] == "complete"
    assert done["revisits_completed"] == 2
    assert [p["pass_number"] for p in done["passes"]] == [2, 3]
    all_scenarios = (
        done["initial_scenario_ids"] +
        [row["scenario"]["scenario_id"] for p in done["passes"] for row in p["results"]]
    )
    assert len(all_scenarios) == len(set(all_scenarios))
    assert done["passes"][1]["reverse_observations"] == 4 * 28
    with pytest.raises(CinematicSimError, match="completed"):
        advance_queue(third, probes=4)


def test_duplicate_archive_is_refused_and_two_sources_are_fifo(tmp_path):
    a, b, _ = archived(tmp_path, source_id="first_scene")
    c, d, _ = archived(tmp_path, source_id="second_scene")
    q = create_queue(a, b)
    with pytest.raises(CinematicSimError, match="duplicate"):
        enqueue(q, a, b)
    combined = enqueue(q, c, d)
    assert len(combined["entries"]) == 2
    staged = advance_queue(combined, max_entries=1, probes=2)
    assert [e["revisits_completed"] for e in staged["entries"]] == [1, 0]
    assert verify_queue(staged)["pending_second_pass"] == 1


def test_immutable_source_and_receipt_tampering_fail_closed(tmp_path):
    source, report, _ = archived(tmp_path)
    queued = create_queue(source, report)
    changed = deepcopy(queued)
    changed["entries"][0]["initial_case_count"] = 999
    with pytest.raises(CinematicSimError, match="digest mismatch"):
        verify_queue(changed)
    report.write_text(report.read_text() + " ", encoding="utf-8")
    with pytest.raises(CinematicSimError, match="changed after queue admission"):
        advance_queue(queued, probes=2)


def test_second_and_third_pass_dont_claim_new_model_training(tmp_path):
    source, report, _ = archived(tmp_path)
    state = advance_queue(create_queue(source, report), probes=8)
    drafts = retraining_review_drafts(state)
    assert all(not d["model_optimizer_eligible"] and not d["model_training_performed"]
               and d["independent_examples_added"] == 0 for d in drafts)
    assert all(d["pass_number"] == 2 and d["source_project_id"] == "original_quest"
               and d["review_status"] == "quarantined_needs_independent_labels"
               for d in drafts)
    assert state["optimizer_updates"] == 0
    assert state["serving_weights_modified"] is False


def test_snapshot_determinism_and_forward_backward_audit_counts(tmp_path):
    scene_path, campaign_path, _ = archived(tmp_path)
    first = create_queue(scene_path, campaign_path)
    a = advance_queue(first, probes=6, workers=1)
    b = advance_queue(first, probes=6, workers=1)
    assert a["queue_sha256"] == b["queue_sha256"]
    assert a["entries"][0]["passes"] == b["entries"][0]["passes"]
    stage = a["entries"][0]["passes"][0]
    assert stage["forward_observations"] == stage["reverse_observations"]
    assert stage["new_camera_trace_digests"] <= stage["scenarios_executed"]


def test_operator_cli_persists_immutable_snapshots(tmp_path):
    source, report, _ = archived(tmp_path)
    queue_a = tmp_path / "queue0.json"
    queue_b = tmp_path / "queue1.json"
    queue_c = tmp_path / "queue2.json"
    drafts = tmp_path / "review.jsonl"
    assert main(["--create", "--scene", str(source), "--archive", str(report),
                 "--output", str(queue_a)]) == 0
    assert main(["--advance", "--queue", str(queue_a), "--probes", "4",
                 "--output", str(queue_b), "--draft-output", str(drafts)]) == 0
    assert main(["--inspect", "--queue", str(queue_b)]) == 0
    assert main(["--advance", "--queue", str(queue_b), "--probes", "4",
                 "--output", str(queue_c)]) == 0
    second = json.loads(queue_b.read_text(encoding="utf-8"))
    third = json.loads(queue_c.read_text(encoding="utf-8"))
    assert verify_queue(second, verify_sources=True)["pending_third_pass"] == 1
    assert verify_queue(third, verify_sources=True)["complete_sources"] == 1
    assert queue_a.is_file() and queue_b.is_file() and queue_c.is_file()
    assert main(["--advance", "--queue", str(queue_c), "--output", str(queue_a)]) == 2


def test_parallel_workers_reproduce_the_same_source_bound_return(tmp_path):
    source, report, _ = archived(tmp_path)
    q = create_queue(source, report)
    one = advance_queue(q, probes=4, workers=1)
    two = advance_queue(q, probes=4, workers=2)
    assert one["entries"][0]["passes"] != [] and one["queue_sha256"] != ""
    assert one["entries"][0]["passes"][0]["source_digest"] == (
        two["entries"][0]["passes"][0]["source_digest"])
    assert [r["trace_digest"] for r in one["entries"][0]["passes"][0]["results"]] == [
        r["trace_digest"] for r in two["entries"][0]["passes"][0]["results"]]
