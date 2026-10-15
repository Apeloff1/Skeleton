"""Bounded local neural world model using *actual replay-verified* ROM traces.

This is a real trainable two-hidden-layer MLP for measured next-observation
deltas and one-step source reward, NOT a pretrained language-model update.
It does not write to Jeeves transformer weights. Training evidence and
candidate weights remain separate from application production authority.

No torch, GPU, network, third-party ROM, proprietary firmware or native
library install is performed here. All numerical work is deterministic
CPython floats, bounded before allocation, with episode-grouped holdout.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .game_learning import _digest

SCHEMA = "skeleton.game.emulator_neural_world_model.v1"
REPORT_SCHEMA = "skeleton.game.emulator_neural_training_report.v1"


class EmulatorNeuralError(ValueError):
    pass


@dataclass(frozen=True)
class NeuralWorldConfig:
    seed: int = 0
    width: int = 20
    epochs: int = 8
    minibatch: int = 16
    learning_rate: float = 0.003
    weight_decay: float = 0.0001
    clip_gradient: float = 3.0
    max_samples: int = 2048
    min_relative_holdout_gain: float = 0.01
    max_compute_units: int = 50_000_000

    def __post_init__(self) -> None:
        for key, minimum, maximum in (
            ("seed", 0, 2**63 - 1),
            ("width", 4, 64),
            ("epochs", 1, 40),
            ("minibatch", 1, 64),
            ("max_samples", 32, 8192),
            ("max_compute_units", 100_000, 300_000_000),
        ):
            item = getattr(self, key)
            if type(item) is not int or not minimum <= item <= maximum:
                raise EmulatorNeuralError(f"{key} outside bounded neural training capacity")
        for key, minimum, maximum in (
            ("learning_rate", 0.00001, 0.05),
            ("weight_decay", 0.0, 0.1),
            ("clip_gradient", 0.1, 100.0),
            ("min_relative_holdout_gain", 0.0, 0.5),
        ):
            item = getattr(self, key)
            if type(item) not in (int, float) or not math.isfinite(item) or not minimum <= item <= maximum:
                raise EmulatorNeuralError(f"{key} outside finite neural optimization capacity")


def _numeric(value: Any, label: str, limit: float = 1e9) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or abs(value) > limit:
        raise EmulatorNeuralError(f"{label} not finite in bounded training range")
    return float(value)


def _check_receipt(receipt: Mapping[str, Any]) -> None:
    if (
        type(receipt) is not dict
        or receipt.get("training_commit") is not True
        or type(receipt.get("actual_steps")) is not int
        or receipt["actual_steps"] < 1
        or receipt.get("actual_tabular_q_updates") != receipt["actual_steps"]
        or not isinstance(receipt.get("scrutiny_checks"), Mapping)
        or len(receipt["scrutiny_checks"]) != 10
        or not all(value is True for value in receipt["scrutiny_checks"].values())
    ):
        raise EmulatorNeuralError("unverified or uncommitted source episode cannot train neural parameters")
    digest = receipt.get("receipt_digest")
    if type(digest) is not str or digest != _digest({k: v for k, v in receipt.items() if k != "receipt_digest"}):
        raise EmulatorNeuralError("replayed training custody receipt digest differs")


def verify_neural_training_sources(
    evidence: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], tuple[str, ...], tuple[str, ...], str]:
    """Strictly reconstruct both independently written outputs and run custody."""
    if not isinstance(evidence, Mapping) or not isinstance(policy, Mapping):
        raise EmulatorNeuralError("typed policy and exact evidence file are required")
    snapshot = dict(policy)
    actual_policy_sha = snapshot.pop("snapshot_digest", None)
    if type(actual_policy_sha) is not str or _digest(snapshot) != actual_policy_sha:
        raise EmulatorNeuralError("policy snapshot canonical checksum differs")
    if (
        evidence.get("policy_snapshot_digest") != actual_policy_sha
        or evidence.get("source_lineage", {}).get("rights_acknowledged") is not True
        or policy.get("source_lineage", {}).get("rights_acknowledged") is not True
        or evidence.get("status") not in (
            "observed_q_and_visual_learning_plateau", "budget_exhausted_before_saturation"
        )
        or evidence.get("actual_neural_parameter_updates") != 0
        or evidence.get("environment") != policy.get("environment")
    ):
        raise EmulatorNeuralError("source rights, training status, policy or environment identity differs")
    # The training CLI saves the policy separately. Reconstitute the exact
    # source report and prove it, rather than trusting a naked dataset JSON.
    raw = dict(evidence)
    claimed = raw.pop("report_digest", None)
    raw.pop("evidence_digest", None)
    raw.pop("policy_snapshot_digest", None)
    raw["policy_snapshot"] = dict(policy)
    if type(claimed) is not str or _digest(raw) != claimed:
        raise EmulatorNeuralError("source evidence/parent policy report identity differs")
    expected_evidence = dict(evidence)
    evidence_digest = expected_evidence.pop("evidence_digest", None)
    if type(evidence_digest) is not str or evidence_digest != _digest(expected_evidence):
        raise EmulatorNeuralError("separate source evidence file checksum differs")
    docs = evidence.get("audited_run_receipts")
    dataset = evidence.get("neural_candidate_dataset")
    if not isinstance(docs, list) or not 3 <= len(docs) <= 256:
        raise EmulatorNeuralError("world-model training needs at least three actual independently audited episodes")
    if not isinstance(dataset, Mapping) or dataset.get("training_executed") is not False or dataset.get("weights_updated") != 0:
        raise EmulatorNeuralError("source dataset is not an unchanged train-only candidate")
    samples = dataset.get("candidate_samples")
    if not isinstance(samples, list) or not 32 <= len(samples) <= 8192:
        raise EmulatorNeuralError("insufficient or oversized native replay-verified training samples")
    if dataset.get("training_sample_count") != len(samples) or dataset.get("dataset_digest") != _digest(samples):
        raise EmulatorNeuralError("training-only candidate dataset fingerprint differs")
    receipt_map = {}
    for receipt in docs:
        _check_receipt(receipt)
        trace_digest = receipt.get("trace_digest")
        if not isinstance(trace_digest, str) or len(trace_digest) != 64 or trace_digest in receipt_map:
            raise EmulatorNeuralError("episode trace identity is invalid or repeated")
        receipt_map[trace_digest] = receipt
    if len(docs) != evidence.get("run_count") or len(docs) != len(policy.get("episodes", [])):
        raise EmulatorNeuralError("source policy committed episode count differs")
    summary_map = {item.get("trace_digest"): item for item in policy["episodes"]}
    if set(summary_map) != set(receipt_map):
        raise EmulatorNeuralError("source training receipts do not bind committed policy episodes")
    descriptor = policy.get("environment", {})
    features = descriptor.get("observation_bins")
    actions = descriptor.get("actions")
    if (
        not isinstance(features, Mapping) or not 1 <= len(features) <= 32
        or not isinstance(actions, list) or not 2 <= len(actions) <= 32
        or len(set(actions)) != len(actions)
    ):
        raise EmulatorNeuralError("finite numeric source environment features and actions required")
    feature_order = tuple(features)
    action_order = tuple(actions)
    observed = set()
    tallies = {key: 0 for key in receipt_map}
    validated = []
    for raw_sample in samples:
        if not isinstance(raw_sample, Mapping) or set(raw_sample) != {
            "trace_digest", "environment_digest", "seed", "sequence",
            "observation", "action", "next_observation", "measured_reward",
            "measured_reward_components", "terminated", "truncated", "source",
        }:
            raise EmulatorNeuralError("candidate training schema differs")
        trace = raw_sample["trace_digest"]
        if (
            trace not in receipt_map or raw_sample["environment_digest"] != descriptor["environment_digest"]
            or raw_sample["source"] != "independently_replayed_emulator_transition"
            or raw_sample["seed"] != summary_map[trace].get("seed")
            or type(raw_sample["sequence"]) is not int
            or not 1 <= raw_sample["sequence"] <= receipt_map[trace]["actual_steps"]
            or type(raw_sample["terminated"]) is not bool
            or type(raw_sample["truncated"]) is not bool
        ):
            raise EmulatorNeuralError("candidate example lacks original verified source binding")
        key = (trace, raw_sample["sequence"])
        if key in observed:
            raise EmulatorNeuralError("duplicate replay segment cannot multiply neural training weight")
        observed.add(key)
        tallies[trace] += 1
        action = raw_sample["action"]
        previous, next_ = raw_sample["observation"], raw_sample["next_observation"]
        rewards = raw_sample["measured_reward_components"]
        if (
            action not in action_order
            or not isinstance(previous, Mapping) or set(previous) != set(features)
            or not isinstance(next_, Mapping) or set(next_) != set(features)
            or not isinstance(rewards, Mapping) or set(rewards) != set(descriptor["reward_components"])
        ):
            raise EmulatorNeuralError("sample features, reward dimensions or controller action differ")
        x = tuple(_numeric(previous[name], "recorded observation") for name in feature_order)
        y = tuple(_numeric(next_[name], "recorded next observation") for name in feature_order)
        reward = _numeric(raw_sample["measured_reward"], "measured real reward")
        if reward != math.fsum(_numeric(v, "reward component") for v in rewards.values()):
            raise EmulatorNeuralError("recorded reward is not a real component sum")
        validated.append({
            "trace_digest": trace,
            "sequence": raw_sample["sequence"],
            "features": x,
            "next_features": y,
            "action_index": action_order.index(action),
            "reward": reward,
        })
    if any(tallies[key] != receipt_map[key]["actual_steps"] for key in receipt_map):
        raise EmulatorNeuralError("source episode has missing/extra ordered transitions")
    return validated, feature_order, action_order, claimed


def _split(
    samples: list[dict[str, Any]], config: NeuralWorldConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    trace_ids = sorted({sample["trace_digest"] for sample in samples},
                       key=lambda trace: _digest(["holdout", config.seed, trace]))
    if len(trace_ids) < 3:
        raise EmulatorNeuralError("at least three independently measured episode groups required")
    holdout_count = max(1, len(trace_ids) // 4)
    holdout = set(trace_ids[:holdout_count])
    validation = [sample for sample in samples if sample["trace_digest"] in holdout]
    training = [sample for sample in samples if sample["trace_digest"] not in holdout]
    # Bound CPU work *after* splitting by episode; never silently train on
    # heldout data or leak heldout scaling parameters into the candidate.
    if len(training) > config.max_samples:
        grouped = sorted(training, key=lambda sample: _digest([
            "training_subsample", config.seed, sample["trace_digest"], sample["sequence"]
        ]))
        training = grouped[:config.max_samples]
    if not training or not validation or len(training) < 16:
        raise EmulatorNeuralError("episode-isolated train/evaluation dataset is insufficient")
    return training, validation, {
        "partition_method": "sha256_seeded_episode_group_isolation",
        "source_trace_groups": len(trace_ids),
        "train_trace_groups": len({item["trace_digest"] for item in training}),
        "heldout_trace_groups": len(holdout),
        "train_source_examples": len(training),
        "heldout_source_examples": len(validation),
        "train_digest": _digest([(item["trace_digest"], item["sequence"]) for item in training]),
        "heldout_digest": _digest([(item["trace_digest"], item["sequence"]) for item in validation]),
        "heldout_never_used_to_fit_normalizer": True,
    }


def _normalizer(rows: list[dict[str, Any]]) -> tuple[list[float], list[float], float, list[float]]:
    dim = len(rows[0]["features"])
    mu = [math.fsum(row["features"][i] for row in rows) / len(rows) for i in range(dim)]
    std = [
        max(0.001, math.sqrt(
            math.fsum((row["features"][i] - mu[i]) ** 2 for row in rows) / len(rows)
        ))
        for i in range(dim)
    ]
    reward_scale = max(0.001, max(abs(item["reward"]) for item in rows))
    return mu, std, reward_scale, [0.0] * dim


def _prepare(
    sample: Mapping[str, Any], mu: list[float], std: list[float],
    reward_scale: float, action_count: int,
) -> tuple[list[float], list[float]]:
    observation = sample["features"]
    x = [max(-8.0, min(8.0, (value - mu[i]) / std[i]))
         for i, value in enumerate(observation)]
    x.extend(1.0 if i == sample["action_index"] else 0.0 for i in range(action_count))
    target = [max(-8.0, min(8.0, sample["reward"] / reward_scale))]
    target.extend(
        max(-8.0, min(8.0, (sample["next_features"][i] - observation[i]) / std[i]))
        for i in range(len(observation))
    )
    return x, target


def _layout(n_input: int, width: int, n_output: int) -> list[tuple[str, int]]:
    return [
        ("w1", width * n_input), ("b1", width),
        ("w2", width * width), ("b2", width),
        ("w3", n_output * width), ("b3", n_output),
    ]


def _init_parameters(n_input: int, width: int, n_output: int, seed: int) -> dict[str, list[float]]:
    rng = random.Random(seed)
    parameter = {}
    for name, length in _layout(n_input, width, n_output):
        fan = n_input if name == "w1" else width
        value = math.sqrt(2 / fan)
        parameter[name] = (
            [rng.uniform(-value, value) for _ in range(length)]
            if name.startswith("w") else [0.0] * length
        )
    return parameter


def _forward(
    parameters: Mapping[str, list[float]], x: list[float], width: int, output_count: int,
) -> tuple[list[float], list[float], list[float]]:
    n = len(x)
    h1 = []
    for row in range(width):
        offset = row * n
        h1.append(math.tanh(
            math.fsum(parameters["w1"][offset + i] * x[i] for i in range(n))
            + parameters["b1"][row]
        ))
    h2 = []
    for row in range(width):
        offset = row * width
        h2.append(math.tanh(
            math.fsum(parameters["w2"][offset + j] * h1[j] for j in range(width))
            + parameters["b2"][row]
        ))
    out = []
    for row in range(output_count):
        offset = row * width
        out.append(
            math.fsum(parameters["w3"][offset + j] * h2[j] for j in range(width))
            + parameters["b3"][row]
        )
    return h1, h2, out


def _gradient(
    p: Mapping[str, list[float]], x: list[float], target: list[float],
    width: int,
) -> tuple[float, dict[str, list[float]]]:
    h1, h2, out = _forward(p, x, width, len(target))
    error = [(y - goal) for y, goal in zip(out, target, strict=True)]
    loss = math.fsum(value * value for value in error) / len(error)
    derivative = [2 * item / len(error) for item in error]
    grad = {name: [0.0] * len(items) for name, items in p.items()}
    for row, value in enumerate(derivative):
        grad["b3"][row] = value
        offset = row * width
        for col in range(width):
            grad["w3"][offset + col] = value * h2[col]
    d2 = []
    for col in range(width):
        total = math.fsum(
            derivative[row] * p["w3"][row * width + col]
            for row in range(len(target))
        )
        d2.append(total * (1 - h2[col] ** 2))
    for row, value in enumerate(d2):
        grad["b2"][row] = value
        offset = row * width
        for col in range(width):
            grad["w2"][offset + col] = value * h1[col]
    d1 = []
    for col in range(width):
        total = math.fsum(d2[row] * p["w2"][row * width + col] for row in range(width))
        d1.append(total * (1 - h1[col] ** 2))
    for row, value in enumerate(d1):
        grad["b1"][row] = value
        offset = row * len(x)
        for col in range(len(x)):
            grad["w1"][offset + col] = value * x[col]
    return loss, grad


def _loss(
    rows: list[tuple[list[float], list[float]]],
    parameters: Mapping[str, list[float]],
    width: int,
) -> float:
    if not rows:
        raise EmulatorNeuralError("empty actual evaluation partition")
    results = []
    for x, target in rows:
        output = _forward(parameters, x, width, len(target))[2]
        results.append(math.fsum((a - b) ** 2 for a, b in zip(output, target, strict=True)) / len(target))
    mean = math.fsum(results) / len(results)
    if not math.isfinite(mean) or mean > 1e10:
        raise EmulatorNeuralError("candidate world model diverged numerically")
    return mean


def _baseline_loss(
    train: list[tuple[list[float], list[float]]],
    valid: list[tuple[list[float], list[float]]],
) -> float:
    out_count = len(train[0][1])
    average = [
        math.fsum(target[i] for _, target in train) / len(train)
        for i in range(out_count)
    ]
    return math.fsum(
        math.fsum((value - average[i]) ** 2 for i, value in enumerate(target)) / out_count
        for _, target in valid
    ) / len(valid)


def train_neural_world_from_evidence(
    evidence: Mapping[str, Any], policy: Mapping[str, Any], *,
    config: NeuralWorldConfig = NeuralWorldConfig(),
    cancel: Callable[[], bool] | None = None,
    authorize: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute actual bounded neural gradient updates on checksum-bound ROM receipts."""
    if not isinstance(config, NeuralWorldConfig):
        raise EmulatorNeuralError("neural world optimizer needs finite typed controls")
    samples, features, actions, source_digest = verify_neural_training_sources(evidence, policy)
    training, validation, partition = _split(samples, config)
    mean, std, reward_scale, _ = _normalizer(training)
    train_rows = [_prepare(item, mean, std, reward_scale, len(actions)) for item in training]
    heldout_rows = [_prepare(item, mean, std, reward_scale, len(actions)) for item in validation]
    n_input, n_output, width = len(features) + len(actions), len(features) + 1, config.width
    # The naive dense Python backprop kernel grows quadratically with hidden
    # width. Bound its actual expected train-only sample count before any
    # optimizer allocation. A budget failure does not create a checkpoint.
    expected_compute_units = (
        config.epochs * len(train_rows)
        * (width * width + width * (n_input + n_output))
    )
    if expected_compute_units > config.max_compute_units:
        raise EmulatorNeuralError(
            "requested pure-Python neural workload exceeds the explicit preflight compute budget"
        )
    if cancel is not None and cancel():
        raise EmulatorNeuralError("neural optimization cancelled before first step")
    if authorize is not None:
        authorize()
    params = _init_parameters(n_input, width, n_output, config.seed)
    moments = {name: [0.0] * len(items) for name, items in params.items()}
    squared = {name: [0.0] * len(items) for name, items in params.items()}
    optimizer_steps = 0
    gradient_evaluations = 0
    history = []
    baseline = _baseline_loss(train_rows, heldout_rows)
    pre_loss = _loss(heldout_rows, params, width)
    for epoch in range(config.epochs):
        order = list(range(len(train_rows)))
        random.Random(int(_digest(["epoch", config.seed, epoch])[:15], 16)).shuffle(order)
        total_train_loss = 0.0
        for batch_start in range(0, len(order), config.minibatch):
            if cancel is not None and cancel():
                raise EmulatorNeuralError("neural optimization cancelled before an optimizer minibatch")
            if authorize is not None:
                authorize()
            indices = order[batch_start:batch_start + config.minibatch]
            gradients = {name: [0.0] * len(values) for name, values in params.items()}
            for index in indices:
                observation, target = train_rows[index]
                loss, grad = _gradient(params, observation, target, width)
                if not math.isfinite(loss):
                    raise EmulatorNeuralError("nonfinite measured world-model training loss")
                total_train_loss += loss
                gradient_evaluations += 1
                for name in gradients:
                    for j, value in enumerate(grad[name]):
                        gradients[name][j] += value / len(indices)
            norm = math.sqrt(math.fsum(
                value * value for values in gradients.values() for value in values
            ))
            if not math.isfinite(norm):
                raise EmulatorNeuralError("neural gradient norm is nonfinite")
            factor = min(1.0, config.clip_gradient / norm) if norm > 0 else 1.0
            optimizer_steps += 1
            beta1, beta2 = 0.9, 0.999
            bias1, bias2 = 1 - beta1 ** optimizer_steps, 1 - beta2 ** optimizer_steps
            for name, values in params.items():
                for j in range(len(values)):
                    g = gradients[name][j] * factor
                    moments[name][j] = beta1 * moments[name][j] + (1 - beta1) * g
                    squared[name][j] = beta2 * squared[name][j] + (1 - beta2) * (g * g)
                    m = moments[name][j] / bias1
                    v = squared[name][j] / bias2
                    values[j] -= config.learning_rate * (
                        m / (math.sqrt(v) + 1e-8)
                        + config.weight_decay * values[j]
                    )
                    if not math.isfinite(values[j]) or abs(values[j]) > 1e9:
                        raise EmulatorNeuralError("world-model neural parameter exceeded safe bounds")
        # Validation is only observational, never used for gradient updates
        # or selecting a best epoch. Fixed epoch budget preserves isolation.
        heldout = _loss(heldout_rows, params, width)
        history.append({
            "epoch": epoch + 1,
            "actual_training_samples_processed": len(train_rows),
            "train_mse": total_train_loss / len(train_rows),
            "heldout_mse_observed_only": heldout,
            "actual_optimizer_steps": optimizer_steps,
            "actual_gradient_evaluations": gradient_evaluations,
        })
    final = _loss(heldout_rows, params, width)
    relative = (baseline - final) / max(baseline, 1e-12)
    quality = (
        "candidate_predictive_gain_measured"
        if relative >= config.min_relative_holdout_gain and final < pre_loss
        else "candidate_failed_heldout_benchmark"
    )
    model = {
        "schema_version": SCHEMA,
        "network": "two_hidden_layer_tanh_dense_reward_and_observation_delta",
        "source_evidence_digest": source_digest,
        "source_policy_snapshot_digest": policy["snapshot_digest"],
        "source_environment_digest": evidence["environment"]["environment_digest"],
        "observation_features": list(features),
        "actions": list(actions),
        "input_dimensions": n_input,
        "hidden_width": width,
        "output_dimensions": n_output,
        "normalization_means_train_only": mean,
        "normalization_std_train_only": std,
        "reward_scale_train_only": reward_scale,
        "parameters": params,
        "parameter_count": sum(len(values) for values in params.values()),
        "real_optimizer_steps": optimizer_steps,
        "gradient_evaluations": gradient_evaluations,
        "actual_neural_parameter_training_executed": True,
        "production_model_promotion_authorized": False,
        "not_a_jeeves_transformer_update": True,
        "heldout_results_not_used_for_optimization": True,
        "measured_predictive_gate": quality,
    }
    model["model_digest"] = _digest(model)
    report = {
        "schema_version": REPORT_SCHEMA,
        "world_model_digest": model["model_digest"],
        "parent_emulator_evidence_digest": source_digest,
        "partition": partition,
        "baseline_train_mean_predictor_holdout_mse": baseline,
        "initial_untrained_network_holdout_mse": pre_loss,
        "final_network_holdout_mse": final,
        "relative_reduction_vs_mean_baseline": relative,
        "candidate_status": quality,
        "recorded_epochs": history,
        "optimizer": {
            "kind": "bounded pure_python_adamw",
            "minibatch": config.minibatch,
            "epochs": config.epochs,
            "learning_rate": config.learning_rate,
            "weight_decay": config.weight_decay,
            "gradient_clip_global_norm": config.clip_gradient,
            "seed": config.seed,
            "actual_preflight_compute_units": expected_compute_units,
            "maximum_approved_compute_units": config.max_compute_units,
        },
        "real_neural_optimizer_steps": optimizer_steps,
        "real_processed_source_training_examples": gradient_evaluations,
        "production_model_promotion": False,
        "learned_objective": "next_numeric_telemetry_delta_and_measured_one_step_reward",
        "does_not_prove": [
            "game win or objective completion", "emulator hardware correctness",
            "long-horizon skill", "transformer or Jeeves model weight promotion",
            "cross-game generalization", "legal title/ROM provenance",
        ],
    }
    report["report_digest"] = _digest(report)
    return model, report



def validate_neural_world_checkpoint(snapshot: Mapping[str, Any]) -> str:
    """Fail closed on adversarial model shapes, not just self-declared SHA256.

    A recomputed digest is not cryptographic authorization. This structural
    check constrains independently imported local candidate files before any
    expensive prediction or source-bound experiment.
    """
    if not isinstance(snapshot, Mapping) or snapshot.get("schema_version") != SCHEMA:
        raise EmulatorNeuralError("typed emulator candidate model is required")
    claimed = snapshot.get("model_digest")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise EmulatorNeuralError("candidate model has no finite digest identity")
    payload = {name: item for name, item in snapshot.items() if name != "model_digest"}
    if _digest(payload) != claimed:
        raise EmulatorNeuralError("candidate model exact parameter checksum differs")
    features = snapshot.get("observation_features")
    actions = snapshot.get("actions")
    width = snapshot.get("hidden_width")
    if (
        not isinstance(features, list) or not 1 <= len(features) <= 32
        or not isinstance(actions, list) or not 2 <= len(actions) <= 32
        or any(type(item) is not str or not 1 <= len(item) <= 64 for item in features + actions)
        or len(set(features)) != len(features)
        or len(set(actions)) != len(actions)
        or type(width) is not int or not 4 <= width <= 64
    ):
        raise EmulatorNeuralError("candidate model sensor, action or hidden basis exceeds physical bounds")
    n_input = len(features) + len(actions)
    n_output = len(features) + 1
    if (
        snapshot.get("input_dimensions") != n_input
        or snapshot.get("output_dimensions") != n_output
        or snapshot.get("network") != "two_hidden_layer_tanh_dense_reward_and_observation_delta"
    ):
        raise EmulatorNeuralError("candidate network topology differs from admitted optimizer")
    normalizer = (
        snapshot.get("normalization_means_train_only"),
        snapshot.get("normalization_std_train_only"),
    )
    if any(not isinstance(values, list) or len(values) != len(features) for values in normalizer):
        raise EmulatorNeuralError("world-model source normalization dimensions differ")
    for values in normalizer:
        if any(type(v) not in (float, int) or not math.isfinite(v) or abs(v) > 1e9 for v in values):
            raise EmulatorNeuralError("world-model source normalization is nonfinite")
    if any(v <= 0 for v in normalizer[1]):
        raise EmulatorNeuralError("world-model normalization has a zero or negative divisor")
    reward_scale = snapshot.get("reward_scale_train_only")
    if type(reward_scale) not in (float, int) or not math.isfinite(reward_scale) or not 0 < reward_scale <= 1e9:
        raise EmulatorNeuralError("world-model reward scale is invalid")
    params = snapshot.get("parameters")
    layout = _layout(n_input, width, n_output)
    if not isinstance(params, Mapping) or set(params) != {name for name, count in layout}:
        raise EmulatorNeuralError("world model has missing or foreign weight tensors")
    sizes = []
    for name, expected in layout:
        values = params[name]
        if not isinstance(values, list) or len(values) != expected:
            raise EmulatorNeuralError("world model tensor dimensions differ from signed architecture")
        if any(type(v) not in (float, int) or not math.isfinite(v) or abs(v) > 1e9 for v in values):
            raise EmulatorNeuralError("world model has nonfinite/oversized numeric parameters")
        sizes.append(expected)
    if (
        snapshot.get("parameter_count") != sum(sizes)
        or type(snapshot.get("real_optimizer_steps")) is not int
        or snapshot["real_optimizer_steps"] < 1
        or type(snapshot.get("gradient_evaluations")) is not int
        or snapshot["gradient_evaluations"] < snapshot["real_optimizer_steps"]
        or snapshot.get("actual_neural_parameter_training_executed") is not True
        or snapshot.get("production_model_promotion_authorized") is not False
        or snapshot.get("not_a_jeeves_transformer_update") is not True
        or snapshot.get("heldout_results_not_used_for_optimization") is not True
        or snapshot.get("measured_predictive_gate") not in (
            "candidate_predictive_gain_measured", "candidate_failed_heldout_benchmark"
        )
    ):
        raise EmulatorNeuralError("candidate optimizer provenance or production safety fields differ")
    for key in ("source_evidence_digest", "source_policy_snapshot_digest", "source_environment_digest"):
        value = snapshot.get(key)
        if type(value) is not str or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise EmulatorNeuralError("world model source-chain digest is invalid")
    return claimed


def infer_neural_world_transition(
    snapshot: Mapping[str, Any], observation: Mapping[str, float], action: str,
) -> dict[str, Any]:
    """Explicitly speculative numerical prediction: NOT a live game step."""
    claimed = validate_neural_world_checkpoint(snapshot)
    features, actions = snapshot["observation_features"], snapshot["actions"]
    if not isinstance(observation, Mapping) or set(observation) != set(features) or action not in actions:
        raise EmulatorNeuralError("predictive input differs from admitted emulator features/actions")
    x = [max(-8, min(8, (_numeric(observation[name], name) - snapshot["normalization_means_train_only"][i])
                         / snapshot["normalization_std_train_only"][i]))
         for i, name in enumerate(features)]
    x.extend(float(action == name) for name in actions)
    result = _forward(snapshot["parameters"], x, snapshot["hidden_width"], len(features) + 1)[2]
    reward = result[0] * snapshot["reward_scale_train_only"]
    expected_next = {
        name: _numeric(observation[name], name)
              + result[i + 1] * snapshot["normalization_std_train_only"][i]
        for i, name in enumerate(features)
    }
    if not math.isfinite(reward) or any(not math.isfinite(v) for v in expected_next.values()):
        raise EmulatorNeuralError("predicted emulator numerical trajectory is invalid")
    return {
        "model_digest": claimed,
        "action": action,
        "predicted_one_step_reward": reward,
        "predicted_next_observation": expected_next,
        "status": "speculative_model_prediction_NOT_measured_native_emulator",
        "production_action_authorized": False,
        "no_hardware_or_game_success_certification": True,
    }
