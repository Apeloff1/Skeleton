"""Deterministic fixtures for genuine numeric emulator-world neural gradient updates.

Only synthetic source structures are used. Actual local ROM execution and
native emulator readiness remain separate independent acceptance obligations.
"""
import copy
import hashlib
import json
import math
import unittest

from skeleton.jeeves.game_emulator_neural_world import (
    EmulatorNeuralError, NeuralWorldConfig, infer_neural_world_transition,
    train_neural_world_from_evidence, verify_neural_training_sources,
)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fixture():
    spec = {
        "environment_id": "synthetic-source",
        "environment_digest": "f" * 64,
        "actions": ["idle", "a", "left"],
        "observation_bins": {
            "screen_mean": [0.25, 0.5, 0.75],
            "visual_change": [0.1, 0.5],
            "step_fraction": [0.25, 0.5, 0.75],
        },
        "reward_components": ["visual_change"],
        "max_episode_steps": 12,
    }
    policy = {
        "schema_version": "fixture-policy",
        "environment": spec,
        "source_lineage": {"rights_acknowledged": True, "operator": "fixture"},
        "episodes": [],
    }
    receipts = []
    samples = []
    for episode in range(8):
        trace = _digest(["trace", episode])
        seed = episode + 42
        policy["episodes"].append({
            "trace_digest": trace, "seed": seed,
            "steps": 12, "episode_id": str(episode),
        })
        receipt = {
            "trace_digest": trace, "seed": seed,
            "actual_steps": 12,
            "actual_tabular_q_updates": 12,
            "training_commit": True,
            "scrutiny_checks": {"check_" + str(i): True for i in range(10)},
        }
        receipt["receipt_digest"] = _digest(receipt)
        receipts.append(receipt)
        for index in range(1, 13):
            action = ("idle", "a", "left")[(index + episode) % 3]
            x = min(1.0, (index + episode) / 24)
            current = {
                "screen_mean": x,
                "visual_change": 0.1 * ((index + episode) % 5),
                "step_fraction": (index - 1) / 12,
            }
            reward = 0.15 if action == "idle" else 0.85 if action == "a" else 0.35
            following = {
                "screen_mean": min(1.0, x + (0.12 if action == "a" else 0.03)),
                "visual_change": reward,
                "step_fraction": index / 12,
            }
            samples.append({
                "trace_digest": trace,
                "environment_digest": spec["environment_digest"],
                "seed": seed, "sequence": index,
                "observation": current, "action": action,
                "next_observation": following,
                "measured_reward": reward,
                "measured_reward_components": {"visual_change": reward},
                "terminated": False,
                "truncated": index == 12,
                "source": "independently_replayed_emulator_transition",
            })
    policy["snapshot_digest"] = _digest(policy)
    dataset = {
        "schema_version": "skeleton.game.emulator_neural_candidate_data.v1",
        "format": "finite_numeric_observation_action_reward_pairs",
        "source": "replayed_emulator_q_training_only",
        "training_sample_count": len(samples),
        "train_only_no_heldout_examples": True,
        "candidate_samples": samples,
        "dataset_digest": _digest(samples),
        "training_executed": False,
        "weights_updated": 0,
        "production_promotion_authorized": False,
    }
    report = {
        "schema_version": "skeleton.game.emulator_training_lab.v1",
        "source_lineage": {"rights_acknowledged": True, "operator": "fixture"},
        "status": "budget_exhausted_before_saturation",
        "actual_neural_parameter_updates": 0,
        "environment": spec,
        "run_count": len(receipts),
        "audited_run_receipts": receipts,
        "neural_candidate_dataset": dataset,
        "policy_snapshot": policy,
    }
    report["report_digest"] = _digest(report)
    evidence = {key: value for key, value in report.items() if key != "policy_snapshot"}
    evidence["policy_snapshot_digest"] = policy["snapshot_digest"]
    evidence["evidence_digest"] = _digest(evidence)
    return evidence, policy


class MeasuredNeuralWorldModelTests(unittest.TestCase):
    def test_real_neural_gradient_updates_and_grouped_heldout(self):
        evidence, policy = fixture()
        samples, features, actions, source = verify_neural_training_sources(evidence, policy)
        self.assertEqual(len(samples), 96)
        self.assertEqual(len(features), 3)
        self.assertEqual(len(actions), 3)
        self.assertEqual(source, evidence["report_digest"])
        model, report = train_neural_world_from_evidence(
            evidence, policy,
            config=NeuralWorldConfig(seed=3, width=8, epochs=12, minibatch=8),
        )
        self.assertTrue(model["actual_neural_parameter_training_executed"])
        self.assertGreater(model["real_optimizer_steps"], 0)
        self.assertGreater(model["gradient_evaluations"], 0)
        self.assertEqual(model["model_digest"], report["world_model_digest"])
        self.assertGreater(report["partition"]["heldout_trace_groups"], 0)
        self.assertGreater(report["partition"]["train_trace_groups"], 0)
        self.assertTrue(report["partition"]["heldout_never_used_to_fit_normalizer"])
        self.assertTrue(math.isfinite(report["final_network_holdout_mse"]))
        self.assertFalse(model["production_model_promotion_authorized"])
        self.assertTrue(model["not_a_jeeves_transformer_update"])
        predicted = infer_neural_world_transition(
            model,
            {"screen_mean": 0.35, "visual_change": 0.2, "step_fraction": 0.25},
            "a",
        )
        self.assertTrue(math.isfinite(predicted["predicted_one_step_reward"]))
        self.assertFalse(predicted["production_action_authorized"])
        self.assertIn("NOT_measured", predicted["status"])

    def test_training_evidence_tampering_is_not_a_source_receipt(self):
        evidence, policy = fixture()
        evidence["neural_candidate_dataset"]["candidate_samples"][0]["measured_reward"] = 999
        with self.assertRaises(EmulatorNeuralError):
            verify_neural_training_sources(evidence, policy)

    def test_policy_or_rights_mismatch_fails(self):
        evidence, policy = fixture()
        policy["source_lineage"]["rights_acknowledged"] = False
        with self.assertRaises(EmulatorNeuralError):
            verify_neural_training_sources(evidence, policy)

    def test_holdout_inference_rejects_mutated_candidate_model(self):
        evidence, policy = fixture()
        model, report = train_neural_world_from_evidence(
            evidence, policy,
            config=NeuralWorldConfig(seed=3, width=8, epochs=1, minibatch=16),
        )
        model["parameters"]["w1"][0] += 0.1
        with self.assertRaises(EmulatorNeuralError):
            infer_neural_world_transition(
                model, {
                    "screen_mean": 0.2, "visual_change": 0.1, "step_fraction": 0.1
                }, "idle",
            )

    def test_optimizer_work_budget_refuses_large_unbounded_python_run(self):
        evidence, policy = fixture()
        with self.assertRaises(EmulatorNeuralError):
            train_neural_world_from_evidence(
                evidence, policy,
                config=NeuralWorldConfig(
                    width=64, epochs=40, max_samples=8192,
                    max_compute_units=100000,
                ),
            )

    def test_optimizer_cancel_refuses_before_any_gradient(self):
        evidence, policy = fixture()
        with self.assertRaises(EmulatorNeuralError):
            train_neural_world_from_evidence(
                evidence, policy,
                config=NeuralWorldConfig(width=8, epochs=2),
                cancel=lambda: True,
            )

    def test_rehashed_malformed_parameter_shapes_are_not_executable(self):
        evidence, policy = fixture()
        model, _ = train_neural_world_from_evidence(
            evidence, policy,
            config=NeuralWorldConfig(seed=3, width=8, epochs=1, minibatch=16),
        )
        model["parameters"]["w1"].pop()
        model["parameter_count"] -= 1
        model["model_digest"] = _digest({k: v for k, v in model.items() if k != "model_digest"})
        with self.assertRaises(EmulatorNeuralError):
            infer_neural_world_transition(
                model, {
                    "screen_mean": 0.2, "visual_change": 0.1,
                    "step_fraction": 0.1,
                }, "idle",
            )

    def test_rehashed_oversized_model_metadata_is_not_executable(self):
        evidence, policy = fixture()
        model, _ = train_neural_world_from_evidence(
            evidence, policy,
            config=NeuralWorldConfig(seed=3, width=8, epochs=1, minibatch=16),
        )
        model["hidden_width"] = 100000
        model["model_digest"] = _digest({k: v for k, v in model.items() if k != "model_digest"})
        with self.assertRaises(EmulatorNeuralError):
            infer_neural_world_transition(
                model, {
                    "screen_mean": 0.2, "visual_change": 0.1,
                    "step_fraction": 0.1,
                }, "idle",
            )

    def test_neural_optimization_is_strictly_bounded(self):
        with self.assertRaises(EmulatorNeuralError):
            NeuralWorldConfig(width=512)
        with self.assertRaises(EmulatorNeuralError):
            NeuralWorldConfig(max_samples=100000)
        with self.assertRaises(EmulatorNeuralError):
            NeuralWorldConfig(epochs=100000)


if __name__ == "__main__":
    unittest.main()
