"""Active simulator campaign acceptance, adversarial and leakage tests."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.training.jeeves_adaptive_sim_training import (
    SCHEMA, ATTACKS, WEATHER, SITUATIONS,
    _scenario, _run_case, _environment,
    draft_scenarios, run_campaign, retraining_drafts,
    validate_scenario, verify_campaign, main,
)
from skeleton.testing.test_jeeves_cinematic_simulation import scene
from skeleton.ai.training.jeeves_cinematic_simulation import CinematicSimError


def test_coverage_guided_drafts_span_situations_weather_and_attacks():
    plans = draft_scenarios(scene(), budget=48, seed=13)
    assert len(plans) == 48
    assert len({r["scenario_id"] for r in plans}) == 48
    assert set(SITUATIONS) <= {r["situation"] for r in plans}
    assert len({r["weather"] for r in plans}) >= 4
    assert len({r["attack"] for r in plans}) >= 5
    assert all(validate_scenario(r) == r for r in plans)
    assert plans == draft_scenarios(scene(), budget=48, seed=13)


def test_environmental_and_adversarial_rehearsal_has_real_frame_evidence():
    source = scene()
    storm = _scenario("pursuit", "storm", "night", "high_wind",
                      90, -30, 40, 1000, 30, 0)
    outcome = _run_case(source, storm, 100)
    assert outcome["reverse_audit_passed"]
    assert outcome["frames_executed"] == 28
    assert outcome["risk_counts"]["visibility_loss"] > 0
    assert outcome["risk_counts"]["time_critical_mobility"] > 0
    assert outcome["risk_counts"]["night_low_light_readability"] > 0
    assert outcome["risk_counts"]["pursuit_lagging_camera"] > 0
    assert outcome["source_replay_receipt"]
    assert outcome["independent_model_training"] is False
    assert outcome["rendered_environment"] is False


def test_adaptive_feedback_budget_counterfactual_and_reverse_counts():
    result = run_campaign(scene(), budget=12, seed=5, workers=1)
    assert result["schema_version"] == SCHEMA
    assert result["simulations_executed"] == 13
    assert result["stratified_runs"] == 6
    assert result["feedback_guided_runs"] == 6
    assert result["forward_observations"] == result["reverse_observations"] == 13*28
    assert result["coverage_feature_count"] > 20
    assert result["source_project_independence_count"] == 1
    assert len({r["scenario"]["scenario_id"] for r in result["cases"]}) == 12
    assert verify_campaign(result)["reverse_audit_complete"]
    assert not result["trained_candidate_weights"]


def test_retraining_drafts_are_quarantined_and_grouped_by_source():
    report = run_campaign(scene(), budget=8, seed=8)
    drafts = retraining_drafts(report)
    assert drafts and len(drafts) % 3 == 0
    groups = {}
    for row in drafts:
        groups.setdefault(row["evidence_group"], []).append(row)
        assert row["source_project_id"] == "original_quest"
        assert row["optimizer_eligible"] is False
        assert row["training_steps_executed"] == 0
        assert row["review_status"] == "quarantined_needs_independent_label"
    assert all(len(rows) == 3 for rows in groups.values())
    assert not report["independent_model_quality_benchmark_complete"]


def test_forged_scenarios_and_campaign_receipts_rejected():
    report = run_campaign(scene(), budget=4)
    forged = deepcopy(report)
    forged["cases"][0]["risk_severity"] = 999999
    with pytest.raises(CinematicSimError, match="SHA mismatch"):
        verify_campaign(forged)
    invalid = deepcopy(report["cases"][0]["scenario"])
    invalid["weather"] = "unsupported_weather"
    with pytest.raises(CinematicSimError, match="unknown situation"):
        validate_scenario(invalid)
    long_scene = deepcopy(scene())
    for index, shot in enumerate(long_scene["shots"]):
        shot["duration_ms"] = 30000
        shot["start_ms"] = 30000*index
    with pytest.raises(CinematicSimError, match="frame budget"):
        run_campaign(long_scene, budget=256, frame_ms=25)


def test_process_isolation_matches_sequential_campaign_results():
    serial = run_campaign(scene(), budget=6, seed=3, workers=1)
    parallel = run_campaign(scene(), budget=6, seed=3, workers=2)
    assert parallel["parallel_workers_requested"] == 2
    assert serial["risk_family_frequency"] == parallel["risk_family_frequency"]
    assert serial["highest_risk_cases"] == parallel["highest_risk_cases"]
    assert [row["trace_digest"] for row in serial["cases"]] == [
        row["trace_digest"] for row in parallel["cases"]]


def test_cli_returns_replayable_evidence_and_quarantined_review_files(tmp_path):
    source = tmp_path / "scene.json"
    source.write_text(json.dumps(scene()))
    receipt = tmp_path / "campaign.json"
    drafts = tmp_path / "drafts.jsonl"
    assert main(["--scene", str(source), "--output", str(receipt),
                 "--draft-output", str(drafts), "--budget", "4"]) == 0
    saved = json.loads(receipt.read_text())
    assert verify_campaign(saved)["count"] == 4
    queued = [json.loads(line) for line in drafts.read_text().splitlines()]
    assert queued and all(not r["optimizer_eligible"] for r in queued)
    assert main(["--audit-report", str(receipt)]) == 0
    assert main(["--scene", str(source), "--budget", "0"]) == 2
