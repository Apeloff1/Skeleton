"""No fake game wins: source-bound triangle auditing and adversarial corruption tests."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.ai.training.rom_study import (
    BATCH_SCHEMA, _save_new, verified_rom_receipt, RomStudyError,
)
from skeleton.jeeves.game_learning import _digest
from skeleton.jeeves.game_emulator_training_lab import SCHEMA as LAB_SCHEMA
from skeleton.jeeves.game_emulator_triangle import (
    LENSES, TrainingTriangleError, build_training_triangle, verify_training_triangle,
)


def _sealed(data):
    result = dict(data)
    result["receipt_digest"] = _digest(data)
    return result


def _report(*, count=2, same_frame=False, counterfactual=True):
    environment = {"environment_digest": "a" * 64}
    policy = {"environment": environment}
    policy["snapshot_digest"] = _digest(policy)
    episodes = []
    samples = []
    for i in range(count):
        trace = f"{i + 1:064x}"
        numeric_projection = {
            "sequence": 1, "observation": {"visual_change": 0.0},
            "action": "right", "next_observation": {"visual_change": 0.75},
            "reward": 0.2, "reward_components": {"progress": 0.2},
            "terminated": False, "truncated": True,
        }
        projection = _digest(numeric_projection)
        frame = ("f" * 64 if same_frame else f"{i + 10:064x}")
        receipt = {
            "run_index": i, "angle": ["exploration", "adversarial"][i % 2],
            "trace_digest": trace, "seed": i + 100,
            "actual_steps": 1, "actual_tabular_q_updates": 1,
            "actual_replay_steps": 1, "training_commit": True,
            "scrutiny_checks": {f"check_{j}": True for j in range(10)},
            "final_snapshot_digest": "b" * 64,
            "reverse_checkpoints": [{
                "replayed_steps": 1, "end_state_matches": True,
                "ending_snapshot_digest": "b" * 64,
            }],
            "verified_training_projection_sha256": [projection],
            "modalities": [{
                "sequence": 1, "actual_frame_sha256": frame,
                "state_signature": _digest(["observation", i]),
                "observed_audio_rms": 0.25,
                "measured_visual_change": 0.75,
            }],
            "counterfactual_probes": ([{
                "actual_frame_sha256": "e" * 64,
                "used_as_policy_update": False,
            }] if counterfactual else []),
            "multi_controller_probes": [],
            "game_success_verified": False,
            "model_neural_weights_updated": 0,
        }
        episodes.append(_sealed(receipt))
        samples.append({
            "source": "independently_replayed_emulator_transition",
            "trace_digest": trace,
            "sequence": 1,
            "seed": i + 100,
            "verified_training_projection_sha256": projection,
            "environment_digest": environment["environment_digest"],
            "observation": numeric_projection["observation"],
            "action": numeric_projection["action"],
            "next_observation": numeric_projection["next_observation"],
            "measured_reward": numeric_projection["reward"],
            "measured_reward_components": numeric_projection["reward_components"],
            "terminated": numeric_projection["terminated"],
            "truncated": numeric_projection["truncated"],
        })
    data = {
        "train_only_no_heldout_examples": True, "training_executed": False,
        "weights_updated": 0, "production_promotion_authorized": False,
        "candidate_samples": samples,
        "training_sample_count": len(samples),
        "dataset_digest": _digest(samples),
    }
    source = {
        "schema_version": LAB_SCHEMA, "status": "budget_exhausted_before_saturation",
        "source_lineage": {"rights_acknowledged": True},
        "environment": environment,
        "policy_snapshot": policy,
        "audited_run_receipts": episodes,
        "run_count": count,
        "actual_training_steps": count,
        "actual_q_table_updates": count,
        "actual_neural_parameter_updates": 0,
        "neural_candidate_dataset": data,
        "boomerang_replay_receipts": [],
        "heldout_evaluation": {"heldout": True},
    }
    source["report_digest"] = _digest(source)
    return source


def _reseal_report(report):
    report["report_digest"] = _digest({
        k: v for k, v in report.items() if k != "report_digest"
    })


def test_triangle_amplifies_lenses_without_inventing_game_samples():
    source = _report(count=2, same_frame=True)
    triangle = build_training_triangle(source)
    verify_training_triangle(source, triangle)
    assert len(triangle["episode_lens_references"]) == 2
    assert triangle["lens_catalog"] == list(LENSES)
    assert triangle["source_diversity"]["unique_observed_frame_hashes"] == 1
    assert triangle["source_diversity"]["unique_measured_training_transitions"] == 2
    assert triangle["training"]["dataset_rows_after_lens_amplification"] == 2
    assert triangle["repeat_and_simulation_accounting"]["verified_reverse_replay_steps"] == 2
    assert triangle["repeat_and_simulation_accounting"]["real_counterfactual_probe_count"] == 2
    assert triangle["training"]["additional_neural_optimizer_steps_from_triangle"] == 0
    assert triangle["training"]["production_jeeves_weight_updates"] == 0
    assert triangle["training"]["semantic_video_review_done"] is False
    assert triangle["training"]["independent_ai_critic_review_done"] is False
    assert triangle["source_diversity"]["curriculum_lenses_exercised"] == 2


def test_adversarial_lens_queue_keeps_missing_native_simulations_explicit():
    triangle = build_training_triangle(_report(count=1, counterfactual=False))
    assert any(row["kind"] == "no_counterfactual_native_probe"
               for row in triangle["adversarial_challenge_queue"])
    assert sum(c["kind"] == "unobserved_curriculum_angle"
               for c in triangle["adversarial_challenge_queue"]) == 9


def test_modified_replay_receipt_rejected_even_when_outer_report_rehashed():
    report = _report()
    report["audited_run_receipts"][0]["actual_tabular_q_updates"] = 0
    _reseal_report(report)
    with pytest.raises(TrainingTriangleError, match="receipt digest"):
        build_training_triangle(report)


def test_cross_episode_sample_rejected_even_with_rehashed_dataset():
    report = _report()
    report["neural_candidate_dataset"]["candidate_samples"][1]["trace_digest"] = (
        report["audited_run_receipts"][0]["trace_digest"]
    )
    report["neural_candidate_dataset"]["dataset_digest"] = _digest(
        report["neural_candidate_dataset"]["candidate_samples"]
    )
    _reseal_report(report)
    with pytest.raises(TrainingTriangleError, match="cross-source"):
        build_training_triangle(report)


def test_counterfactual_cannot_be_counted_as_q_policy_update():
    report = _report()
    episode = report["audited_run_receipts"][0]
    episode["counterfactual_probes"][0]["used_as_policy_update"] = True
    episode["receipt_digest"] = _digest({k: v for k, v in episode.items()
                                           if k != "receipt_digest"})
    _reseal_report(report)
    with pytest.raises(TrainingTriangleError, match="simulation probes"):
        build_training_triangle(report)


def test_triangle_falsified_viewing_or_critic_witness_rejected():
    report = _report()
    triangle = build_training_triangle(report)
    forged = deepcopy(triangle)
    forged["episode_lens_references"][0]["companion_viewing"][
        "semantic_video_witness_verified"
    ] = True
    forged["training"]["independent_ai_critic_review_done"] = True
    forged["triangle_digest"] = _digest({k: v for k, v in forged.items()
                                           if k != "triangle_digest"})
    with pytest.raises(TrainingTriangleError, match="no longer matches"):
        verify_training_triangle(report, forged)


def test_native_receipt_revalidates_triangle_before_accepting_resume(tmp_path):
    report = _report()
    triangle = build_training_triangle(report)
    source_sha = "1" * 64
    row = {
        "schema_version": BATCH_SCHEMA, "source_sha256": source_sha,
        "run_identity": "2" * 64,
        "production_weights_modified": False,
        "model_promotion_authorized": False, "neural_weights_updated": 0,
        "candidate_evidence": report,
        "neural_world": {"status": "not_requested", "production_jeeves_weight_updates": 0},
        "training_triangle": triangle,
    }
    target = tmp_path / "rom-triangle.json"
    _save_new(target, row)
    assert verified_rom_receipt(target, expected_source_sha256=source_sha)[
        "training_triangle_status"
    ]["jeeves_ai_playing_and_simulation"] == "verified_actual_native_gameplay"
    target.unlink()
    row["training_triangle"] = {**triangle, "training": {
        **triangle["training"], "production_jeeves_weight_updates": 1
    }}
    _save_new(target, row)
    with pytest.raises(RomStudyError, match="training triangle"):
        verified_rom_receipt(target, expected_source_sha256=source_sha)

def test_rehashed_numeric_change_cannot_bypass_replay_projection():
    report = _report()
    samples = report["neural_candidate_dataset"]["candidate_samples"]
    samples[0]["measured_reward"] = 999.0
    report["neural_candidate_dataset"]["dataset_digest"] = _digest(samples)
    _reseal_report(report)
    with pytest.raises(TrainingTriangleError, match="numeric features"):
        build_training_triangle(report)
