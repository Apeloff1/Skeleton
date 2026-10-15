"""Multi-seed emulator neural ensembles with SAME source episode holdout.

All members receive EXACTLY the same audited source traces, training-group
partition, normalization rules and evaluation examples. Different seeds
initialize distinct trainable world models. Empirical disagreement is
measured on actually observed heldout ROM transitions; prospective predictions
are speculative until verified by real native execution. Never promote a
Jeeves provider model, Q policy, weights or game-success certificate here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .game_learning import _digest
from .game_emulator_neural_world import (
    EmulatorNeuralError,
    NeuralWorldConfig,
    _forward,
    _prepare,
    _baseline_loss,
    _split,
    train_neural_world_from_evidence,
    validate_neural_world_checkpoint,
    verify_neural_training_sources,
)

SCHEMA = "skeleton.game.emulator_world_ensemble.v1"


class EmulatorEnsembleError(EmulatorNeuralError):
    pass


@dataclass(frozen=True)
class EmulatorEnsembleConfig:
    seed: int = 0
    holdout_seed: int = 42
    members: int = 3
    width: int = 12
    epochs: int = 6
    minibatch: int = 16
    max_samples: int = 2048
    max_compute_units_per_member: int = 20_000_000
    max_calibration_samples: int = 128
    max_mean_normalized_spread: float = 0.2

    def __post_init__(self) -> None:
        for key, low, high in (
            ("seed", 0, 2**63 - 1),
            ("holdout_seed", 0, 2**63 - 1),
            ("members", 3, 7),
            ("width", 4, 64),
            ("epochs", 1, 40),
            ("minibatch", 1, 64),
            ("max_samples", 32, 8192),
            ("max_compute_units_per_member", 100000, 300000000),
            ("max_calibration_samples", 16, 512),
        ):
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise EmulatorEnsembleError(f"{key} outside bounded source-executed world-model ensemble range")
        if (
            type(self.max_mean_normalized_spread) not in (float, int)
            or not math.isfinite(self.max_mean_normalized_spread)
            or not 0.001 <= self.max_mean_normalized_spread <= 3.0
        ):
            raise EmulatorEnsembleError("ensemble prediction disagreement limit differs")
        if self.members * self.epochs * self.max_samples * self.width**2 > 300_000_000:
            raise EmulatorEnsembleError("combined multi-seed CPU work envelope exceeds bound")


def _normalized_predictions(
    snapshot: Mapping[str, Any], observation: Mapping[str, float], action: str,
) -> list[float]:
    feature_order = snapshot["observation_features"]
    mean = snapshot["normalization_means_train_only"]
    std = snapshot["normalization_std_train_only"]
    inputs = [
        max(-8.0, min(8.0, (observation[key] - mean[i]) / std[i]))
        for i, key in enumerate(feature_order)
    ]
    inputs.extend(float(action == name) for name in snapshot["actions"])
    output = _forward(
        snapshot["parameters"], inputs, snapshot["hidden_width"],
        len(feature_order) + 1,
    )[2]
    if any(not math.isfinite(value) or abs(value) > 1e8 for value in output):
        raise EmulatorEnsembleError("candidate ensemble predicted nonfinite numeric state")
    return output


def _ensemble_statistics(
    models: list[Mapping[str, Any]], observation: Mapping[str, float], action: str,
) -> dict[str, Any]:
    observed = [_normalized_predictions(model, observation, action) for model in models]
    count = len(observed)
    means = [
        math.fsum(row[j] for row in observed) / count
        for j in range(len(observed[0]))
    ]
    squared_spread = [
        math.fsum((row[j] - means[j])**2 for row in observed) / count
        for j in range(len(means))
    ]
    normalized_spread = math.sqrt(math.fsum(squared_spread) / len(squared_spread))
    model = models[0]
    predicted_reward = means[0] * model["reward_scale_train_only"]
    predicted_next = {
        name: observation[name] + means[i + 1] * model["normalization_std_train_only"][i]
        for i, name in enumerate(model["observation_features"])
    }
    if not math.isfinite(predicted_reward) or any(not math.isfinite(v) for v in predicted_next.values()):
        raise EmulatorEnsembleError("unnormalized neural predictions are nonfinite")
    return {
        "normalized_prediction_means": means,
        "normalized_rms_member_disagreement": normalized_spread,
        "mean_predicted_reward": predicted_reward,
        "mean_predicted_next_observation": predicted_next,
        "member_count": count,
    }


def train_emulator_neural_ensemble(
    evidence: Mapping[str, Any], policy: Mapping[str, Any], *,
    config: EmulatorEnsembleConfig = EmulatorEnsembleConfig(),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute independently initialized candidate optimizers on one heldout split."""
    if not isinstance(config, EmulatorEnsembleConfig):
        raise EmulatorEnsembleError("explicit typed neural ensemble limits required")
    source, features, actions, parent_digest = verify_neural_training_sources(evidence, policy)
    base_config = NeuralWorldConfig(
        seed=config.seed,
        holdout_seed=config.holdout_seed,
        width=config.width,
        epochs=config.epochs,
        minibatch=config.minibatch,
        max_samples=config.max_samples,
        max_compute_units=config.max_compute_units_per_member,
    )
    training, heldout, partition = _split(source, base_config)
    # Holdout is used only to measure completed models, never to update them.
    chosen_heldout = sorted(
        heldout,
        key=lambda sample: _digest([
            "ensemble_calibration", config.holdout_seed,
            sample["trace_digest"], sample["sequence"],
        ]),
    )[: config.max_calibration_samples]
    candidates = []
    training_reports = []
    for index in range(config.members):
        initialization_seed = int(
            _digest(["neural_member", config.seed, index])[:15], 16
        )
        sub_config = NeuralWorldConfig(
            seed=initialization_seed,
            holdout_seed=config.holdout_seed,
            width=config.width,
            epochs=config.epochs,
            minibatch=config.minibatch,
            max_samples=config.max_samples,
            max_compute_units=config.max_compute_units_per_member,
        )
        model, member_report = train_neural_world_from_evidence(
            evidence, policy, config=sub_config,
        )
        if model["source_partition_digest"] != _digest(partition):
            raise EmulatorEnsembleError("member changed the shared source training/holdout partition")
        validate_neural_world_checkpoint(model)
        candidates.append(model)
        training_reports.append(member_report)
    if len({model["model_digest"] for model in candidates}) != config.members:
        raise EmulatorEnsembleError("independently initialized members have duplicate parameter identities")
    heldout_mse = []
    heldout_disagreement = []
    for item in chosen_heldout:
        observed = dict(zip(features, item["features"], strict=True))
        action = actions[item["action_index"]]
        actual_delta = [
            item["reward"] / candidates[0]["reward_scale_train_only"],
        ] + [
            (item["next_features"][j] - item["features"][j])
            / candidates[0]["normalization_std_train_only"][j]
            for j in range(len(features))
        ]
        prediction = _ensemble_statistics(candidates, observed, action)
        average = prediction["normalized_prediction_means"]
        heldout_mse.append(
            math.fsum((actual_delta[j] - average[j])**2 for j in range(len(average)))
            / len(average)
        )
        heldout_disagreement.append(prediction["normalized_rms_member_disagreement"])
    mean_holdout_mse = math.fsum(heldout_mse) / len(heldout_mse)
    mean_spread = math.fsum(heldout_disagreement) / len(heldout_disagreement)
    # Fair comparison: use a constant predictor fitted to exactly the same
    # source TRAIN subset and scored on exactly the same selected holdout rows.
    # Previous full-heldout model baselines may have different sample counts.
    reference = candidates[0]
    mean = reference["normalization_means_train_only"]
    std = reference["normalization_std_train_only"]
    scale = reference["reward_scale_train_only"]
    train_vectors = [
        _prepare(row, mean, std, scale, len(actions)) for row in training
    ]
    selected_vectors = [
        _prepare(row, mean, std, scale, len(actions)) for row in chosen_heldout
    ]
    mean_baseline = _baseline_loss(train_vectors, selected_vectors)
    successful = sum(
        report["candidate_status"] == "candidate_predictive_gain_measured"
        for report in training_reports
    )
    passed = (
        successful >= 2 and
        mean_holdout_mse < mean_baseline and
        mean_spread <= config.max_mean_normalized_spread
    )
    ensemble = {
        "schema_version": SCHEMA,
        "parent_source_evidence_digest": parent_digest,
        "environment_digest": evidence["environment"]["environment_digest"],
        "source_rom_training_policy_digest": policy["snapshot_digest"],
        "training_partition_digest": _digest(partition),
        "shared_train_trace_digest": partition["train_digest"],
        "shared_heldout_trace_digest": partition["heldout_digest"],
        "shared_holdout_seed": config.holdout_seed,
        "observation_features": list(features),
        "actions": list(actions),
        "members": candidates,
        "member_model_digests": [model["model_digest"] for model in candidates],
        "max_mean_normalized_spread": config.max_mean_normalized_spread,
        "mean_measured_source_holdout_spread": mean_spread,
        "mean_measured_ensemble_holdout_mse": mean_holdout_mse,
        "source_holdout_baseline_mse": mean_baseline,
        "qualified_for_source_confirmation": passed,
        "actual_neural_training_executed_if_report_is_from_local_operator": True,
        "production_weights_updated": 0,
        "production_or_model_promotion_authorized": False,
    }
    ensemble["ensemble_digest"] = _digest(ensemble)
    report = {
        "schema_version": "skeleton.game.emulator_world_ensemble_report.v1",
        "ensemble_digest": ensemble["ensemble_digest"],
        "source_evidence_digest": parent_digest,
        "actual_independently_trained_members": len(candidates),
        "member_seed_receipts": [
            {
                "model_digest": model["model_digest"],
                "actual_neural_optimizer_steps": model["real_optimizer_steps"],
                "training_report_digest": member_report["report_digest"],
                "heldout_mse": member_report["final_network_holdout_mse"],
                "qualified_prediction": member_report["candidate_status"],
            }
            for model, member_report in zip(candidates, training_reports, strict=True)
        ],
        "source_group_partition": partition,
        "measured_holdout_examples_used_for_calibration_only": len(chosen_heldout),
        "ensemble_heldout_mse": mean_holdout_mse,
        "ensemble_train_mean_baseline_heldout_mse": mean_baseline,
        "baseline_and_ensemble_compared_on_identical_holdout_samples": True,
        "mean_member_disagreement": mean_spread,
        "max_allowable_disagreement": config.max_mean_normalized_spread,
        "qualified_for_physical_native_confirmation": passed,
        "never_claimed_game_victory_or_semantic_scene_understanding": True,
        "actual_jeeves_production_weight_updates": 0,
        "operator_generated_source_rights_not_independently_verified": True,
    }
    report["report_digest"] = _digest(report)
    return ensemble, report


def predict_world_ensemble(
    ensemble: Mapping[str, Any], observation: Mapping[str, float], action: str,
) -> dict[str, Any]:
    """Epistemically gated proposals, NOT real native emulator transitions."""
    if not isinstance(ensemble, Mapping) or ensemble.get("schema_version") != SCHEMA:
        raise EmulatorEnsembleError("source-bound trained neural ensemble required")
    envelope = dict(ensemble)
    claimed = envelope.pop("ensemble_digest", None)
    if not isinstance(claimed, str) or _digest(envelope) != claimed:
        raise EmulatorEnsembleError("source ensemble parameter custody digest differs")
    members = ensemble.get("members")
    if not isinstance(members, list) or not 3 <= len(members) <= 7:
        raise EmulatorEnsembleError("bounded independent source members required")
    digests = [validate_neural_world_checkpoint(member) for member in members]
    if digests != ensemble.get("member_model_digests") or len(set(digests)) != len(digests):
        raise EmulatorEnsembleError("source ensemble members lack independent provenance")
    if (
        any(member.get("source_environment_digest") != ensemble.get("environment_digest")
            or member.get("source_partition_digest") != ensemble.get("training_partition_digest")
            or member.get("source_partition_holdout_digest") != ensemble.get("shared_heldout_trace_digest")
            or member.get("source_evidence_digest") != ensemble.get("parent_source_evidence_digest")
            or member.get("observation_features") != ensemble.get("observation_features")
            or member.get("actions") != ensemble.get("actions")
            or member.get("normalization_means_train_only") != members[0]["normalization_means_train_only"]
            or member.get("normalization_std_train_only") != members[0]["normalization_std_train_only"]
            or member.get("reward_scale_train_only") != members[0]["reward_scale_train_only"]
            for member in members)
    ):
        raise EmulatorEnsembleError("member changed source ROM, train normalization, action or holdout identity")
    if not isinstance(observation, Mapping) or set(observation) != set(ensemble["observation_features"]):
        raise EmulatorEnsembleError("observed source state differs from trained numeric sensor basis")
    if action not in ensemble["actions"]:
        raise EmulatorEnsembleError("proposed native control is not a trained action")
    if any(type(v) not in (float, int) or not math.isfinite(v) or abs(v) > 1e9 for v in observation.values()):
        raise EmulatorEnsembleError("current source observation is nonfinite")
    result = _ensemble_statistics(members, observation, action)
    threshold = ensemble.get("max_mean_normalized_spread")
    if type(threshold) not in (float, int) or not math.isfinite(threshold) or not 0.001 <= threshold <= 3.0:
        raise EmulatorEnsembleError("model ensemble uncertainty ceiling is invalid")
    is_qualified = ensemble.get("qualified_for_source_confirmation") is True
    return {
        "ensemble_digest": claimed,
        "action": action,
        "speculative_mean_one_step_reward": result["mean_predicted_reward"],
        "speculative_mean_next_observation": result["mean_predicted_next_observation"],
        "source_measured_member_disagreement": result["normalized_rms_member_disagreement"],
        "member_count": len(members),
        "confidence_gate_passed_for_physical_recheck": (
            is_qualified and result["normalized_rms_member_disagreement"] <= threshold
        ),
        "real_native_execution_performed": False,
        "allowed_to_change_real_jeeves_weights": False,
        "model_prediction_cannot_establish_game_success": True,
    }
