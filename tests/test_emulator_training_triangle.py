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


def _fake_native_rgb_observation(frame_sha="a" * 64):
    from skeleton.jeeves.game_emulator_dragon_observer import observe_native_frame
    class Native:
        def inspect_frame(self):
            return {
                "schema_version": "skeleton.game.native_frame_inspection.v1",
                "pixel_sha256": frame_sha,
                "full_resolution_tile_hashes": True,
                "tile_color_statistics_are_sampled": True,
                "native_frames_executed_for_inspection": 0,
                "width": 1, "height": 1, "total_tiles": 1,
                "tiles": [{
                    "samples": 64, "sampled_rgb_mean": [64.0, 128.0, 192.0],
                    "sampled_luminance_range": [92, 92],
                    "sampled_dark_count": 0, "sampled_bright_count": 0,
                    "tile_rgb_sha256": "d" * 64,
                }],
            }
    return observe_native_frame(Native(), expected_frame_sha256=frame_sha)


def test_dragon_observes_pixel_derived_color_and_tile_metrics():
    from skeleton.jeeves.game_emulator_dragon_observer import verify_native_observation
    optical = _fake_native_rgb_observation()
    verify_native_observation(optical, frame_sha256="a" * 64)
    assert optical["sampled_rgb_mean"] == [64.0, 128.0, 192.0]
    assert optical["sampled_luminance_range"] == [92, 92]
    assert optical["pixels_checked_by_existing_native_inspector"] == 1
    assert optical["semantic_entities_inferred"] is False
    assert optical["weights_updated"] == 0


def test_triangle_indexes_real_optical_receipts_but_no_semantic_witness():
    report = _report(count=1)
    episode = report["audited_run_receipts"][0]
    frame = episode["modalities"][0]["actual_frame_sha256"]
    episode["modalities"][0]["dragon_optical"] = _fake_native_rgb_observation(frame)
    episode["receipt_digest"] = _digest({
        k: v for k, v in episode.items() if k != "receipt_digest"
    })
    _reseal_report(report)
    triangle = build_training_triangle(report)
    assert triangle["source_diversity"]["actual_native_rgb24_optical_frames"] == 1
    assert triangle["vertices"]["dragon_companion_viewing"] == (
        "native_pixel_optics_measured_semantic_review_pending"
    )
    assert triangle["episode_lens_references"][0]["grounded_lens_evidence"][
        "visual_state"
    ]["measured_pixel_optics_sha256"] is not None
    assert triangle["training"]["semantic_video_review_done"] is False


def test_tampered_dragon_pixel_metrics_fail_closed():
    report = _report(count=1)
    episode = report["audited_run_receipts"][0]
    frame = episode["modalities"][0]["actual_frame_sha256"]
    witness = _fake_native_rgb_observation(frame)
    witness["sampled_rgb_mean"][0] = 0.0
    episode["modalities"][0]["dragon_optical"] = witness
    episode["receipt_digest"] = _digest({
        k: v for k, v in episode.items() if k != "receipt_digest"
    })
    _reseal_report(report)
    with pytest.raises(ValueError, match="optical"):
        build_training_triangle(report)


def test_native_adversarial_reviewer_runs_three_real_runtime_contract_calls(monkeypatch):
    import json
    from types import SimpleNamespace
    from skeleton.ai.model_runtime import native_llm_runtime
    from skeleton.jeeves.game_emulator_triangle_native_reviewer import (
        run_native_adversarial_review, verify_native_adversarial_review,
    )
    report = _report(count=1)
    triangle = build_training_triangle(report)
    class SimulatedRuntime:
        # Contract mock only; an installed NativeLLMRuntime is required by production.
        model_digest = "e" * 64
        def __init__(self):
            self.calls = 0
        def assert_model_unchanged(self):
            return None
        def generate(self, prompt, config):
            self.calls += 1
            meta = json.loads(prompt.split("\n")[-1])
            attack = meta["attack"]
            payload = json.dumps({
                "trace_sha256": meta["episodes"][0]["trace_sha256"],
                "verdict": "challenge", "attack": attack,
                "rationale": "The observed metadata does not establish generalized mastery.",
            })
            rr = SimpleNamespace(
                model_digest=self.model_digest, seed=config.seed,
                to_dict=lambda: {
                    "model_digest": self.model_digest,
                    "output_digest": "a" * 64, "request_digest": "b" * 64,
                    "seed": config.seed,
                },
            )
            return SimpleNamespace(
                text=payload, generated_ids=(1,),
                replay_receipt=rr,
                to_record=lambda: {
                    "model_digest": self.model_digest,
                    "output_digest": "a" * 64, "request_digest": "b" * 64,
                    "checkpoint_digest": "c" * 64,
                    "generated_token_ids": [1],
                },
            )
    monkeypatch.setattr(native_llm_runtime, "NativeLLMRuntime", SimulatedRuntime)
    fake = SimulatedRuntime()
    result = run_native_adversarial_review(report, triangle, fake, max_new_tokens=48)
    assert fake.calls == 3
    assert result["structured_source_bound_passes"] == 3
    assert result["requested_seed"] == 0
    assert result["requested_max_new_tokens"] == 48
    assert result["reviewer_distinct_from_production_jeeves_verified"] is False
    assert result["production_jeeves_weight_updates"] == 0
    assert result["manual_adjudication_required"] is True
    verify_native_adversarial_review(report, triangle, result)
    result["passes"][1]["interpretation"]["verdict"] = "supported"
    result["review_digest"] = _digest({k: v for k, v in result.items()
                                        if k != "review_digest"})
    with pytest.raises(ValueError, match="finding"):
        verify_native_adversarial_review(report, triangle, result)

def test_adversarial_generated_text_refuses_unhashable_trace():
    from skeleton.jeeves.game_emulator_triangle_native_reviewer import _interpret
    import json
    output = json.dumps({
        "trace_sha256": ["not a digest"],
        "attack": "source_integrity",
        "verdict": "supported",
        "rationale": "This claim cannot be supported by the source evidence.",
    })
    assert _interpret(
        output, attack="source_integrity", traces={"a" * 64}
    )["status"] == "unsupported_claim_or_schema_requires_manual_review"

def test_dragon_temporal_optics_detects_changed_tiles_without_extra_steps():
    from skeleton.jeeves.game_emulator_dragon_observer import (
        observe_native_frame_with_cursor, verify_native_observation,
    )
    class Native:
        frame = 0
        def inspect_frame(self):
            frame = ("a" if self.frame == 0 else "b") * 64
            return {
                "schema_version": "skeleton.game.native_frame_inspection.v1",
                "pixel_sha256": frame,
                "full_resolution_tile_hashes": True,
                "tile_color_statistics_are_sampled": True,
                "native_frames_executed_for_inspection": 0,
                "width": 16, "height": 16, "total_tiles": 16,
                "tiles": [{
                    "samples": 64,
                    "sampled_rgb_mean": [64.0, 128.0, 192.0],
                    "sampled_luminance_range": [92, 92],
                    "sampled_dark_count": 0, "sampled_bright_count": 0,
                    "tile_rgb_sha256": ("c" if self.frame == 0 else "d") * 64,
                } for _ in range(16)],
            }
    environment = Native()
    first, cursor = observe_native_frame_with_cursor(
        environment, expected_frame_sha256="a" * 64,
    )
    assert first["previous_native_frame_sha256"] is None
    environment.frame = 1
    second, _ = observe_native_frame_with_cursor(
        environment, expected_frame_sha256="b" * 64, previous_cursor=cursor,
    )
    verify_native_observation(second, frame_sha256="b" * 64)
    assert second["previous_native_frame_sha256"] == "a" * 64
    assert second["changed_native_rgb_tile_count"] == 16
    assert second["changed_native_rgb_tile_fraction"] == 1.0
    assert second["candidate_full_frame_transition"] is True
    assert second["new_native_steps_for_observation"] == 0

def test_native_reviewer_replay_requires_actual_checkpoint(monkeypatch):
    from skeleton.jeeves.game_emulator_triangle_native_reviewer import (
        replay_native_adversarial_review,
    )
    with pytest.raises(ValueError, match="real local checkpoint"):
        replay_native_adversarial_review(_report(), build_training_triangle(_report()),
                                         {}, object())


def test_temporal_optics_refuse_wrong_prior_native_frame():
    from skeleton.jeeves.game_emulator_dragon_observer import (
        observe_native_frame, observe_native_frame_with_cursor,
    )
    class Native:
        def inspect_frame(self):
            return {
                "schema_version": "skeleton.game.native_frame_inspection.v1",
                "pixel_sha256": "a" * 64,
                "full_resolution_tile_hashes": True,
                "tile_color_statistics_are_sampled": True,
                "native_frames_executed_for_inspection": 0,
                "width": 1, "height": 1, "total_tiles": 1,
                "tiles": [{
                    "samples": 64,
                    "sampled_rgb_mean": [64.0, 128.0, 192.0],
                    "sampled_luminance_range": [92, 92],
                    "sampled_dark_count": 0, "sampled_bright_count": 0,
                    "tile_rgb_sha256": "d" * 64,
                }],
            }
    source = _report(count=2)
    for index, receipt in enumerate(source["audited_run_receipts"]):
        optical = observe_native_frame(
            Native(), expected_frame_sha256="a" * 64,
        )
        if index == 1:
            optical, _ = observe_native_frame_with_cursor(
                Native(), expected_frame_sha256="a" * 64,
                previous_cursor=("b" * 64, 1, 1, ("d" * 64,)),
            )
        receipt["modalities"][0]["actual_frame_sha256"] = "a" * 64
        receipt["modalities"][0]["dragon_optical"] = optical
        receipt["receipt_digest"] = _digest({
            k: v for k, v in receipt.items() if k != "receipt_digest"
        })
    _reseal_report(source)
    with pytest.raises(TrainingTriangleError, match="temporal cursor"):
        build_training_triangle(source)



def test_native_optical_verifier_fail_closed_on_missing_tile_count():
    from skeleton.jeeves.game_emulator_dragon_observer import (
        verify_native_observation,
    )
    witness = _fake_native_rgb_observation()
    witness["tile_count"] = None
    with pytest.raises(ValueError, match="optical"):
        verify_native_observation(witness, frame_sha256="a" * 64)


def test_native_optical_verifier_rejects_rehashed_fake_temporal_fraction():
    from skeleton.jeeves.game_emulator_dragon_observer import (
        verify_native_observation,
    )
    witness = _fake_native_rgb_observation()
    witness["previous_native_frame_sha256"] = "f" * 64
    witness["changed_native_rgb_tile_count"] = 1
    witness["changed_native_rgb_tile_fraction"] = 0.3
    witness["candidate_full_frame_transition"] = True
    witness["observation_digest"] = _digest({
        k: v for k, v in witness.items() if k != "observation_digest"
    })
    with pytest.raises(ValueError, match="tile change"):
        verify_native_observation(witness, frame_sha256="a" * 64)
