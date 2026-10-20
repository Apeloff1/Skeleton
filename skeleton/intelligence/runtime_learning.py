"""Bounded online operational learning for the canonical execution runtime.

This module does no I/O and grants no execution authority. It learns from numeric
terminal telemetry, never from generated praise, prompt contents, or claimed
facts. Its small neural controller produces advice for the execution owner;
provider selection, verification, budgets, and approval remain authoritative.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "skeleton.runtime.learning.v1"
FEATURE_SCHEMA = "skeleton.runtime.learning.features.v1"
LAYERS = ((12, 16), (16, 8), (8, 3))
PARAMETER_COUNT = sum(inputs * outputs + outputs for inputs, outputs in LAYERS)
MAX_COUNTER = 2**53 - 1
MAX_STATE_BYTES = 192 * 1024
OUTPUT_NAMES = ("operational_completion", "resource_failure", "normalized_latency")
LATENCY_REFERENCE_SECONDS = 30.0
DEFAULT_POLICY: dict[str, Any] = {
    "schema_version": SCHEMA,
    "enabled": True,
    "min_samples": 12,
    "replay_capacity": 64,
    "replay_steps": 2,
    "learning_rate": 0.003,
    "gradient_clip": 1.0,
    "max_effort_rounds": 3,
    "target_latency_seconds": 30.0,
    "pressure_threshold": 0.8,
    "uncertainty_ceiling": 0.45,
    "partition_limit": 32,
}


class RuntimeLearningError(ValueError):
    """Learning metadata, policy, or optimizer state is invalid."""


def canonical(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise RuntimeLearningError("learning material must be finite JSON") from exc


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def identifier(value: object, name: str, *, maximum: int = 192) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 for char in value)
    ):
        raise RuntimeLearningError(f"{name} is invalid")
    return value


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise RuntimeLearningError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _finite(value: object, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeLearningError(f"{name} must be finite numeric data")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise RuntimeLearningError(f"{name} must be finite numeric data") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise RuntimeLearningError(f"{name} must be in [{minimum}, {maximum}]")
    return result


def normalize_policy(value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if value is None:
        return dict(DEFAULT_POLICY)
    if not isinstance(value, Mapping) or set(value) - set(DEFAULT_POLICY):
        raise RuntimeLearningError("runtime learning policy fields are invalid")
    policy = {**DEFAULT_POLICY, **value}
    if policy["schema_version"] != SCHEMA or type(policy["enabled"]) is not bool:
        raise RuntimeLearningError("runtime learning policy schema/enabled is invalid")
    for name, low, high in (
        ("min_samples", 4, 10000), ("replay_capacity", 8, 256),
        ("replay_steps", 0, 3), ("max_effort_rounds", 1, 3), ("partition_limit", 1, 128),
    ):
        policy[name] = _integer(policy[name], name, low, high)
    for name, low, high in (
        ("learning_rate", 0.00001, 0.05), ("gradient_clip", 0.01, 5.0),
        ("target_latency_seconds", 0.1, 86400.0), ("pressure_threshold", 0.1, 1.0),
        ("uncertainty_ceiling", 0.05, 0.75),
    ):
        policy[name] = _finite(policy[name], name, low, high)
    return policy


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _stable_provider(value: object) -> dict[str, Any]:
    provider = _mapping(value)
    routes = provider.get("routes", [])
    if not isinstance(routes, (list, tuple)) or len(routes) > 8:
        return {}
    result = []
    for raw in routes:
        route = _mapping(raw)
        activation = _mapping(route.get("local_activation"))
        result.append({
            "provider_id": route.get("provider_id"),
            "model_id": route.get("model_id"),
            "endpoint_digest": route.get("endpoint_digest"),
            "model_digest": activation.get("model_digest"),
            "runtime_digest": activation.get("runtime_digest"),
            "execution_profile_digest": activation.get("execution_profile_digest"),
        })
    return {"mode": provider.get("mode"), "routes": result}


def runtime_learning_identity(request: object, checkpoint_payload: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Derive reusable model partitions while retaining exact source provenance.

    Whole provider binding digests contain execution IDs and cannot identify a
    reusable learner. Stable route/activation fields are selected explicitly.
    Source fingerprints are outcome provenance, never a factual memory store.
    """
    context = _mapping(getattr(request, "context_policy", {}))
    tools = _mapping(getattr(request, "tool_policy", {}))
    tenant = context.get("tenant_id", tools.get("tenant_id"))
    if tenant is None:
        tenant = "unscoped"
    tenant = identifier(tenant, "tenant_id", maximum=512)
    if any(value is not None and value != tenant for value in (context.get("tenant_id"), tools.get("tenant_id"))):
        raise RuntimeLearningError("learning tenant binding differs")
    scope = identifier(context.get("runtime_learning_scope_id", "tenant"), "scope_id")
    task = identifier(context.get("capability", "assistant.chat"), "task_class", maximum=256)
    binding = _mapping(_mapping(checkpoint_payload).get("provider_execution_binding"))
    cooperation = _mapping(binding.get("cooperation"))
    role_providers = _mapping(cooperation.get("role_providers"))
    if binding:
        model = {
            "generator": _stable_provider(binding.get("generator")),
            "verifier": _stable_provider(binding.get("verifier")),
            "roles": {str(role): _stable_provider(value) for role, value in sorted(role_providers.items())},
        }
    else:
        model = {
            "selection": context.get("provider_selection"),
            "legacy_model": context.get("provider_model"),
            "roles": _mapping(context.get("cooperation")).get("roles", {}),
        }
    model_digest = digest(model)
    sources = context.get("source_snapshot", [])
    source_digest = digest(sources)
    partition = digest({"task_class": task, "model_selection_digest": model_digest})
    return {
        "tenant_id": tenant, "scope_id": scope, "task_class": task,
        "model_selection_digest": model_digest, "source_snapshot_digest": source_digest,
        "partition_id": partition,
    }


def _number(value: object, default: float = 0.0, maximum: float = MAX_COUNTER) -> float:
    try:
        return _finite(value, "telemetry", 0.0, maximum)
    except RuntimeLearningError:
        return default


def _log_feature(value: object, ceiling: float) -> float:
    return min(1.0, math.log1p(_number(value, maximum=ceiling * 100)) / math.log1p(ceiling))


def request_features(request: object | None, *, pressure: float = 0.0, resource_budget: Mapping[str, Any] | None = None, requested_rounds: int = 1) -> list[float]:
    """Only pre-dispatch numeric metadata enters the model's feature vector."""
    pressure = _finite(pressure, "pressure", 0.0, 1.0)
    budget = _mapping(resource_budget if resource_budget is not None else getattr(request, "resource_budget", {}))
    context = _mapping(getattr(request, "context_policy", {}))
    tools = _mapping(getattr(request, "tool_policy", {}))
    allowed = tools.get("allowed_tool_ids", [])
    allowed_count = len(allowed) if isinstance(allowed, (list, tuple)) else 0
    sources = context.get("source_snapshot", [])
    source_count = len(sources) if isinstance(sources, (list, tuple)) else 0
    cooperation = _mapping(context.get("cooperation"))
    rounds = _number(cooperation.get("review_rounds", requested_rounds), default=1.0, maximum=3.0)
    objective = getattr(request, "objective", "")
    objective_length = len(objective) if isinstance(objective, str) else 0
    return [
        _log_feature(objective_length, 100000),
        _log_feature(budget.get("max_input_tokens", 32768), 262144),
        _log_feature(budget.get("max_output_tokens", 16384), 65536),
        min(1.0, _number(budget.get("max_model_turns", 8)) / 64.0),
        min(1.0, _number(budget.get("max_tool_calls", 16)) / 64.0),
        min(1.0, allowed_count / 64.0), min(1.0, source_count / 128.0),
        min(1.0, rounds / 3.0), pressure,
        _log_feature(budget.get("max_wall_seconds", budget.get("max_elapsed_seconds", 120)), 86400),
        float(allowed_count > 0), float(context.get("verification_profile") == "evidence_required"),
    ]


def terminal_observation(request: object, result: object, checkpoint_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Convert a canonical terminal result into bounded, content-free telemetry."""
    identity = runtime_learning_identity(request, checkpoint_payload)
    usage = _mapping(getattr(result, "usage", {}))
    budget_charged = _mapping(usage.get("provider_budget_charged"))
    errors = 0

    def numeric(value: object, maximum: float = MAX_COUNTER) -> float:
        nonlocal errors
        try:
            return _finite(value, "terminal telemetry", 0.0, maximum)
        except RuntimeLearningError:
            errors += 1
            return 0.0

    elapsed = numeric(max(0.0, (result.completed_at - request.created_at).total_seconds()), 315576000.0)
    error_code = usage.get("error_code", "")
    if not isinstance(error_code, str) or len(error_code) > 192 or any(ord(char) < 32 for char in error_code):
        errors += 1
        error_code = "invalid_terminal_error_code"
    resource_failure = any(word in error_code for word in (
        "budget", "deadline", "capacity", "overload", "exceeded_reservation", "resource", "rate_limit",
    ))
    status = str(result.status)
    payload = _mapping(checkpoint_payload)
    admission = _mapping(payload.get("runtime_learning"))
    pressure = _number(admission.get("pressure"), maximum=1.0)
    metrics = {
        "elapsed_seconds": elapsed,
        "input_tokens": numeric(budget_charged.get("input_tokens", 0)),
        "output_tokens": numeric(budget_charged.get("output_tokens", 0)),
        "provider_attempts": numeric(budget_charged.get("provider_attempts", 0)),
        "cost_usd": numeric(budget_charged.get("cost_usd", 0), 1000000000.0),
        "model_turns": numeric(usage.get("model_turns", 0)),
        "tool_calls": numeric(usage.get("tool_calls", 0)),
        "resource_failure": int(resource_failure), "telemetry_errors": errors,
    }
    result_payload = result.as_dict()
    return {
        "schema_version": SCHEMA, **identity,
        "execution_id": identifier(result.execution_id, "execution_id"),
        "request_digest": request.identity_digest, "result_digest": digest(result_payload),
        "outcome_id": digest({"execution_id": result.execution_id, "request_digest": request.identity_digest,
                              "model": identity["model_selection_digest"], "source": identity["source_snapshot_digest"],
                              "result_digest": digest(result_payload)}),
        "status": status, "error_code": error_code,
        "features": request_features(request, pressure=pressure),
        "metrics": metrics, "trainable": status != "cancelled" and errors == 0 and identity["tenant_id"] != "unscoped",
        "observed_at": result.completed_at.isoformat(),
    }


def observation_targets(observation: Mapping[str, Any], policy: Mapping[str, Any]) -> list[float]:
    metrics = _mapping(observation.get("metrics"))
    elapsed = _finite(metrics.get("elapsed_seconds"), "elapsed_seconds", 0, 315576000.0)
    return [
        {"completed": 1.0, "degraded": 0.35, "failed": 0.0, "cancelled": 0.0}.get(str(observation.get("status")), 0.0),
        float(_integer(metrics.get("resource_failure"), "resource_failure", 0, 1)),
        # A fixed target scale keeps replay/model semantics valid when the
        # operator changes their latency objective between executions.
        elapsed / (elapsed + LATENCY_REFERENCE_SECONDS),
    ]


def new_state(seed: str) -> dict[str, Any]:
    generator = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    weights: list[float] = []
    for inputs, outputs in LAYERS:
        limit = math.sqrt(6.0 / (inputs + outputs))
        weights.extend(generator.uniform(-limit, limit) for _ in range(inputs * outputs))
        weights.extend(0.0 for _ in range(outputs))
    return {
        "schema_version": SCHEMA, "feature_schema": FEATURE_SCHEMA,
        "architecture": [12, 16, 8, 3], "weights": weights,
        "optimizer": {"step": 0, "m": [0.0] * PARAMETER_COUNT, "v": [0.0] * PARAMETER_COUNT},
        "observations": 0, "residual_ema": [0.25, 0.25, 0.25],
        "replay": [], "quarantined": False, "quarantine": None,
    }


def _vector(value: object, length: int, name: str, minimum: float, maximum: float) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise RuntimeLearningError(f"{name} shape differs")
    return [_finite(item, name, minimum, maximum) for item in value]


def validate_state(value: object, *, replay_capacity: int = 256) -> dict[str, Any]:
    if not isinstance(value, dict) or len(canonical(value).encode()) > MAX_STATE_BYTES:
        raise RuntimeLearningError("optimizer state exceeds its storage bound")
    if value.get("schema_version") != SCHEMA or value.get("feature_schema") != FEATURE_SCHEMA or value.get("architecture") != [12, 16, 8, 3]:
        raise RuntimeLearningError("optimizer architecture differs")
    _vector(value.get("weights"), PARAMETER_COUNT, "weights", -8.0, 8.0)
    optimizer = _mapping(value.get("optimizer"))
    _integer(optimizer.get("step"), "optimizer step", 0, MAX_COUNTER)
    _vector(optimizer.get("m"), PARAMETER_COUNT, "optimizer first moment", -5.0, 5.0)
    _vector(optimizer.get("v"), PARAMETER_COUNT, "optimizer second moment", 0.0, 25.0)
    _integer(value.get("observations"), "observations", 0, MAX_COUNTER)
    _vector(value.get("residual_ema"), 3, "residual_ema", 0.0, 1.0)
    if type(value.get("quarantined")) is not bool:
        raise RuntimeLearningError("optimizer quarantine flag is invalid")
    replay = value.get("replay")
    if not isinstance(replay, list) or len(replay) > replay_capacity:
        raise RuntimeLearningError("optimizer replay bound differs")
    for sample in replay:
        if not isinstance(sample, dict) or set(sample) != {"outcome_id", "features", "targets"}:
            raise RuntimeLearningError("replay sample shape differs")
        sample_id = identifier(sample["outcome_id"], "outcome_id", maximum=64)
        if len(sample_id) != 64 or any(char not in "0123456789abcdef" for char in sample_id):
            raise RuntimeLearningError("replay outcome identity must be sha256")
        _vector(sample["features"], 12, "features", 0.0, 1.0)
        _vector(sample["targets"], 3, "targets", 0.0, 1.0)
    return value


def _forward(weights: Sequence[float], features: Sequence[float]) -> list[list[float]]:
    activations = [list(features)]
    offset = 0
    for layer, (inputs, outputs) in enumerate(LAYERS):
        previous = activations[-1]
        biases = offset + inputs * outputs
        values = []
        for output in range(outputs):
            value = weights[biases + output] + sum(weights[offset + output * inputs + index] * previous[index] for index in range(inputs))
            values.append(math.tanh(value) if layer < 2 else 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, value)))))
        activations.append(values)
        offset = biases + outputs
    return activations


def _optimize(state: dict[str, Any], sample: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
    weights = state["weights"]
    activations = _forward(weights, sample["features"])
    prediction = activations[-1]
    delta = [(predicted - target) * predicted * (1.0 - predicted) * (2.0 / 3.0) for predicted, target in zip(prediction, sample["targets"], strict=True)]
    gradient = [0.0] * PARAMETER_COUNT
    offsets = []
    offset = 0
    for inputs, outputs in LAYERS:
        offsets.append(offset)
        offset += inputs * outputs + outputs
    for layer in range(2, -1, -1):
        inputs, outputs = LAYERS[layer]
        offset = offsets[layer]
        previous = activations[layer]
        for output in range(outputs):
            for index in range(inputs):
                gradient[offset + output * inputs + index] = delta[output] * previous[index]
            gradient[offset + inputs * outputs + output] = delta[output]
        if layer:
            delta = [sum(weights[offset + output * inputs + index] * delta[output] for output in range(outputs)) * (1.0 - previous[index] ** 2) for index in range(inputs)]
    norm = math.sqrt(sum(value * value for value in gradient))
    scale = min(1.0, float(policy["gradient_clip"]) / max(norm, 1e-12))
    optimizer = state["optimizer"]
    step = min(MAX_COUNTER, int(optimizer["step"]) + 1)
    correction1, correction2 = 1.0 - 0.9**step, 1.0 - 0.999**step
    for index, value in enumerate(gradient):
        value *= scale
        first = optimizer["m"][index] = 0.9 * optimizer["m"][index] + 0.1 * value
        second = optimizer["v"][index] = 0.999 * optimizer["v"][index] + 0.001 * value * value
        update = (first / correction1) / (math.sqrt(second / correction2) + 1e-8)
        weights[index] = max(-8.0, min(8.0, weights[index] - float(policy["learning_rate"]) * (update + 0.00001 * weights[index])))
    optimizer["step"] = step


def quarantine_state(seed: str, *, reason: str, prior_digest: str = "") -> dict[str, Any]:
    state = new_state(seed)
    state["quarantined"] = True
    state["quarantine"] = {"reason": reason[:192], "prior_digest": prior_digest[:64]}
    return state


def learn_outcome(state: dict[str, Any] | None, observation: Mapping[str, Any], policy: Mapping[str, Any], *, seed: str) -> tuple[dict[str, Any], bool]:
    """One canonical sample plus at most three replay updates, deterministically."""
    policy = normalize_policy(policy)
    if state is None:
        state = new_state(seed)
    try:
        validate_state(state)
    except RuntimeLearningError as exc:
        try:
            prior_digest = digest(state)
        except RuntimeLearningError:
            prior_digest = ""
        return quarantine_state(seed, reason=str(exc), prior_digest=prior_digest), False
    state["replay"] = state["replay"][-int(policy["replay_capacity"]):]
    if state["quarantined"] or not policy["enabled"] or observation.get("trainable") is not True:
        return state, False
    sample = {
        "outcome_id": identifier(observation.get("outcome_id"), "outcome_id", maximum=64),
        "features": _vector(observation.get("features"), 12, "features", 0.0, 1.0),
        "targets": observation_targets(observation, policy),
    }
    prediction = _forward(state["weights"], sample["features"])[-1]
    state["residual_ema"] = [0.95 * previous + 0.05 * (predicted - target) ** 2 for previous, predicted, target in zip(state["residual_ema"], prediction, sample["targets"], strict=True)]
    state["observations"] = min(MAX_COUNTER, state["observations"] + 1)
    _optimize(state, sample, policy)
    replay = state["replay"]
    for index in range(min(int(policy["replay_steps"]), len(replay))):
        _optimize(state, replay[(int(state["optimizer"]["step"]) + index) % len(replay)], policy)
    if len(replay) < policy["replay_capacity"]:
        replay.append(sample)
    else:
        # Deterministic reservoir: old failures are not erased by a recent streak.
        slot = int(sample["outcome_id"][:16], 16) % state["observations"]
        if slot < len(replay):
            replay[slot] = sample
    try:
        validate_state(state)
    except RuntimeLearningError as exc:
        return quarantine_state(seed, reason=str(exc)), False
    return state, True


def replay_maintenance(state: dict[str, Any], policy: Mapping[str, Any], *, max_updates: int = 2) -> dict[str, Any]:
    """Bounded idle optimization; does not invent samples or observed outcomes."""
    policy = normalize_policy(policy)
    validate_state(state)
    max_updates = _integer(max_updates, "max_updates", 0, 4)
    if policy["enabled"] and not state["quarantined"]:
        for _ in range(min(max_updates, len(state["replay"]))):
            _optimize(state, state["replay"][int(state["optimizer"]["step"]) % len(state["replay"])], policy)
    validate_state(state)
    return state


def state_readiness(state: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    samples = int(state.get("observations", 0))
    residual = _vector(state.get("residual_ema"), 3, "residual_ema", 0.0, 1.0)
    uncertainty = min(1.0, math.sqrt(sum(residual) / 3.0) + 1.0 / math.sqrt(samples + 1.0))
    quarantined = state.get("quarantined") is True
    readiness = "disabled" if not policy["enabled"] else "quarantined" if quarantined else "ready" if samples >= policy["min_samples"] and uncertainty <= policy["uncertainty_ceiling"] else "cold_start"
    return {"samples": samples, "optimizer_steps": int(_mapping(state.get("optimizer")).get("step", 0)),
            "readiness": readiness, "quarantined": quarantined, "uncertainty": uncertainty,
            "prediction_error": math.sqrt(sum(residual) / 3.0)}


def recommend(state: dict[str, Any] | None, policy: Mapping[str, Any], features: list[float], *, allowed_rounds: int = 1, requested_rounds: int = 1, pressure: float = 0.0) -> dict[str, Any]:
    policy = normalize_policy(policy)
    allowed_rounds = _integer(allowed_rounds, "allowed_rounds", 1, 3)
    requested_rounds = _integer(requested_rounds, "requested_rounds", 1, 3)
    pressure = _finite(pressure, "pressure", 0.0, 1.0)
    _vector(features, 12, "features", 0.0, 1.0)
    rounds = min(requested_rounds, allowed_rounds, policy["max_effort_rounds"])
    result: dict[str, Any] = {
        "schema_version": "skeleton.runtime.learning.recommendation.v1", "advisory_only": True,
        "recommended_rounds": rounds, "requested_rounds": requested_rounds, "allowed_rounds": allowed_rounds,
        "defer_background": pressure >= policy["pressure_threshold"], "pressure": pressure,
        "learned_adjustment": False, "prediction": None, "lessons": [],
        "readiness": "disabled" if not policy["enabled"] else "cold_start", "samples": 0,
        "uncertainty": 1.0, "quarantined": False,
        "authority": {"model_selection": "unchanged", "resource_grants": "unchanged", "verification": "unchanged"},
    }
    if state is None:
        return result
    try:
        validate_state(state)
        result.update(state_readiness(state, policy))
    except RuntimeLearningError:
        result.update({"readiness": "quarantined", "quarantined": True})
        return result
    if result["readiness"] != "ready":
        return result
    values = _forward(state["weights"], features)[-1]
    result["prediction"] = dict(zip(OUTPUT_NAMES, values, strict=True))
    completion, resource_failure, latency = values
    latency_limit = policy["target_latency_seconds"] / (policy["target_latency_seconds"] + LATENCY_REFERENCE_SECONDS)
    result["prediction"]["estimated_latency_seconds"] = min(315576000.0, LATENCY_REFERENCE_SECONDS * latency / max(1e-9, 1.0 - latency))
    lessons = []
    # Advice may conserve user-authorized effort. It never requests extra grants.
    if pressure >= policy["pressure_threshold"] and (resource_failure >= 0.35 or latency >= latency_limit):
        rounds = 1
        lessons.append("reduce_optional_review_under_resource_pressure")
    elif completion >= 0.9 and resource_failure <= 0.15 and requested_rounds > 1:
        rounds = max(1, rounds - 1)
        lessons.append("shorter_review_has_sufficient_operational_confidence")
    elif completion < 0.65 and rounds > 1:
        lessons.append("retain_authorized_review_for_low_completion_confidence")
    if resource_failure >= 0.35:
        lessons.append("schedule_background_work_after_foreground_pressure_falls")
        result["defer_background"] = True
    result.update({"recommended_rounds": min(rounds, allowed_rounds, requested_rounds),
                   "learned_adjustment": rounds != min(requested_rounds, allowed_rounds, policy["max_effort_rounds"]),
                   "lessons": lessons[:4]})
    return result
