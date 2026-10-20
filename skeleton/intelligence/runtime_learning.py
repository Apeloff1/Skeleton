"""Bounded online operational learning for the canonical execution runtime.

This module does no I/O and grants no execution authority. It learns from numeric
terminal telemetry, never from generated praise, prompt contents, or claimed
facts. Its small neural controller produces advice for the execution owner;
provider selection, verification, budgets, and approval remain authoritative.
"""

from __future__ import annotations

import hashlib
import copy
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
CONTROLLER_VERSION = 2
MAX_RECENT_SOURCES = 16
MAX_RECENT_LOSSES = 32
MAX_CHECKPOINT_BYTES = 256 * 1024
CHECKPOINT_SCHEMA = "skeleton.runtime.learning.checkpoint.v1"
OPTIMIZER_CHECKPOINT_SCHEMA = "skeleton.runtime.learning.optimizer_checkpoint.v1"
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
    "retained_outcomes": 10000,
    "outcome_max_age_days": 90,
    "maintenance_receipt_retention": 2048,
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
        ("retained_outcomes", 128, 100000), ("outcome_max_age_days", 1, 3650),
        ("maintenance_receipt_retention", 16, 100000),
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
    state = {
        "schema_version": SCHEMA, "feature_schema": FEATURE_SCHEMA,
        "architecture": [12, 16, 8, 3], "weights": weights,
        "optimizer": {"step": 0, "m": [0.0] * PARAMETER_COUNT, "v": [0.0] * PARAMETER_COUNT},
        "observations": 0, "residual_ema": [0.25, 0.25, 0.25],
        "replay": [], "quarantined": False, "quarantine": None,
    }
    return upgrade_state(state)


def _new_prequential() -> dict[str, Any]:
    return {
        "count": 0, "mean_loss": 0.0, "m2_loss": 0.0,
        "absolute_error_mean": [0.0, 0.0, 0.0], "squared_error_mean": [0.0, 0.0, 0.0],
        "fast_loss": 0.25, "slow_loss": 0.25, "last_loss": 0.0,
        "drift_debt": 0.0, "drift_score": 0.0, "drift_events": 0,
        "drift_active": False, "cooldown_remaining": 0, "stable_observations": 0,
        "last_drift_observation": 0, "recent_losses": [],
    }


def _optimizer_checkpoint(state: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = {
        "schema_version": OPTIMIZER_CHECKPOINT_SCHEMA,
        "weights": list(state["weights"]), "optimizer": copy.deepcopy(state["optimizer"]),
        "observations": int(state.get("observations", 0)),
        "baseline_loss": float(_mapping(state.get("prequential")).get("slow_loss", 0.25)),
        "health_basis": "finite_optimizer_and_prior_prequential_stability",
    }
    return {**checkpoint, "checkpoint_digest": digest(checkpoint)}


def upgrade_state(state: dict[str, Any]) -> dict[str, Any]:
    """Lazily upgrade finite legacy weights without inventing past confidence."""
    if state.get("controller_version") == CONTROLLER_VERSION:
        if "idle_replay_budget" not in state:
            state["idle_replay_budget"] = 0
            if _mapping(state.get("optimizer_cost")).get("maintenance_updates", 0):
                # Older controllers could replay indefinitely between real
                # outcomes. Their last residual does not certify those weights.
                state["fresh_observations"] = 0
                state["prequential"]["drift_active"] = True
                state["prequential"]["cooldown_remaining"] = max(16, state["prequential"]["cooldown_remaining"])
        return state
    if "controller_version" in state:
        raise RuntimeLearningError("controller state version differs")
    state.update({
        "controller_version": CONTROLLER_VERSION, "generation": 0,
        "fresh_observations": 0, "lifetime_observations": int(state.get("observations", 0)),
        "prequential": _new_prequential(), "recent_replay": [],
        "provenance": {"partition_id": "", "model_selection_digest": "", "latest_source_digest": "",
            "recent_sources": [], "source_switches": 0, "last_observation_at": None},
        "optimizer_cost": {"terminal_updates": 0, "replay_updates": 0, "maintenance_updates": 0,
            "total_updates": int(_mapping(state.get("optimizer")).get("step", 0)),
            "deferred_replay_updates": 0, "rollbacks": 0},
        "last_rollback": None,
        "idle_replay_budget": 0,
    })
    state["last_healthy"] = _optimizer_checkpoint(state)
    return state


def _sha(value: object, name: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeLearningError(f"{name} must be sha256")
    return value


def _validate_optimizer(value: object) -> Mapping[str, Any]:
    optimizer = _mapping(value)
    if set(optimizer) != {"step", "m", "v"}:
        raise RuntimeLearningError("optimizer fields differ")
    _integer(optimizer.get("step"), "optimizer step", 0, MAX_COUNTER)
    _vector(optimizer.get("m"), PARAMETER_COUNT, "optimizer first moment", -5.0, 5.0)
    _vector(optimizer.get("v"), PARAMETER_COUNT, "optimizer second moment", 0.0, 25.0)
    return optimizer


def validate_optimizer_checkpoint(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "weights", "optimizer", "observations", "baseline_loss", "health_basis", "checkpoint_digest"}:
        raise RuntimeLearningError("healthy optimizer checkpoint shape differs")
    if value["schema_version"] != OPTIMIZER_CHECKPOINT_SCHEMA or value["health_basis"] != "finite_optimizer_and_prior_prequential_stability":
        raise RuntimeLearningError("healthy optimizer checkpoint schema differs")
    _vector(value["weights"], PARAMETER_COUNT, "checkpoint weights", -8.0, 8.0)
    _validate_optimizer(value["optimizer"])
    _integer(value["observations"], "checkpoint observations", 0, MAX_COUNTER)
    _finite(value["baseline_loss"], "checkpoint loss", 0.0, 1.0)
    if digest({key: item for key, item in value.items() if key != "checkpoint_digest"}) != _sha(value["checkpoint_digest"], "checkpoint_digest"):
        raise RuntimeLearningError("healthy optimizer checkpoint digest differs")
    return value


def _vector(value: object, length: int, name: str, minimum: float, maximum: float) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise RuntimeLearningError(f"{name} shape differs")
    return [_finite(item, name, minimum, maximum) for item in value]


def validate_state(value: object, *, replay_capacity: int = 256) -> dict[str, Any]:
    if not isinstance(value, dict) or len(canonical(value).encode()) > MAX_STATE_BYTES:
        raise RuntimeLearningError("optimizer state exceeds its storage bound")
    allowed_fields = {
        "schema_version", "feature_schema", "architecture", "weights", "optimizer", "observations",
        "residual_ema", "replay", "quarantined", "quarantine", "controller_version", "generation",
        "fresh_observations", "lifetime_observations", "prequential", "recent_replay", "provenance",
        "optimizer_cost", "last_rollback", "last_healthy", "recovery", "last_operator_action",
        "idle_replay_budget",
    }
    if set(value) - allowed_fields:
        raise RuntimeLearningError("optimizer state fields differ")
    if value.get("schema_version") != SCHEMA or value.get("feature_schema") != FEATURE_SCHEMA or value.get("architecture") != [12, 16, 8, 3]:
        raise RuntimeLearningError("optimizer architecture differs")
    _vector(value.get("weights"), PARAMETER_COUNT, "weights", -8.0, 8.0)
    _validate_optimizer(value.get("optimizer"))
    _integer(value.get("observations"), "observations", 0, MAX_COUNTER)
    _vector(value.get("residual_ema"), 3, "residual_ema", 0.0, 1.0)
    if type(value.get("quarantined")) is not bool:
        raise RuntimeLearningError("optimizer quarantine flag is invalid")
    quarantine = value.get("quarantine")
    if quarantine is not None:
        if not isinstance(quarantine, dict) or set(quarantine) != {"reason", "prior_digest"}:
            raise RuntimeLearningError("optimizer quarantine metadata differs")
        if not isinstance(quarantine["reason"], str) or len(quarantine["reason"]) > 192:
            raise RuntimeLearningError("optimizer quarantine reason differs")
        _sha(quarantine["prior_digest"], "quarantined optimizer digest", allow_empty=True)
    replay = value.get("replay")
    recent_replay = value.get("recent_replay", [])
    if not isinstance(replay, list) or not isinstance(recent_replay, list) or len(replay) + len(recent_replay) > replay_capacity:
        raise RuntimeLearningError("optimizer replay bound differs")
    for sample in [*replay, *recent_replay]:
        if not isinstance(sample, dict) or set(sample) != {"outcome_id", "features", "targets"}:
            raise RuntimeLearningError("replay sample shape differs")
        sample_id = identifier(sample["outcome_id"], "outcome_id", maximum=64)
        if len(sample_id) != 64 or any(char not in "0123456789abcdef" for char in sample_id):
            raise RuntimeLearningError("replay outcome identity must be sha256")
        _vector(sample["features"], 12, "features", 0.0, 1.0)
        _vector(sample["targets"], 3, "targets", 0.0, 1.0)
    if "controller_version" not in value:
        return value
    if value["controller_version"] != CONTROLLER_VERSION:
        raise RuntimeLearningError("controller state version differs")
    for name in ("generation", "fresh_observations", "lifetime_observations"):
        _integer(value.get(name), name, 0, MAX_COUNTER)
    if "idle_replay_budget" in value:
        _integer(value["idle_replay_budget"], "idle_replay_budget", 0, 3)
    prequential = _mapping(value.get("prequential"))
    if set(prequential) != set(_new_prequential()):
        raise RuntimeLearningError("prequential fields differ")
    for name in ("count", "drift_events", "cooldown_remaining", "stable_observations", "last_drift_observation"):
        _integer(prequential.get(name), name, 0, MAX_COUNTER)
    for name in ("mean_loss", "fast_loss", "slow_loss", "last_loss", "drift_score"):
        _finite(prequential.get(name), name, 0.0, 1.0)
    _finite(prequential.get("m2_loss"), "loss squared deviations", 0.0, MAX_COUNTER)
    _finite(prequential.get("drift_debt"), "drift debt", 0.0, 100.0)
    _vector(prequential.get("absolute_error_mean"), 3, "absolute_error_mean", 0.0, 1.0)
    _vector(prequential.get("squared_error_mean"), 3, "squared_error_mean", 0.0, 1.0)
    if type(prequential.get("drift_active")) is not bool:
        raise RuntimeLearningError("drift flag differs")
    recent_losses = prequential.get("recent_losses")
    if not isinstance(recent_losses, list) or len(recent_losses) > MAX_RECENT_LOSSES:
        raise RuntimeLearningError("prequential loss window bound differs")
    _vector(recent_losses, len(recent_losses), "recent_losses", 0.0, 1.0)
    provenance = _mapping(value.get("provenance"))
    if set(provenance) != {"partition_id", "model_selection_digest", "latest_source_digest", "recent_sources", "source_switches", "last_observation_at"}:
        raise RuntimeLearningError("source provenance fields differ")
    for name in ("partition_id", "model_selection_digest", "latest_source_digest"):
        _sha(provenance.get(name), name, allow_empty=True)
    _integer(provenance.get("source_switches"), "source_switches", 0, MAX_COUNTER)
    sources = provenance.get("recent_sources")
    if not isinstance(sources, list) or len(sources) > MAX_RECENT_SOURCES:
        raise RuntimeLearningError("source provenance bound differs")
    seen_sources = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"digest", "observations", "last_seen"}:
            raise RuntimeLearningError("source provenance shape differs")
        source_digest = _sha(source["digest"], "source digest")
        if source_digest in seen_sources:
            raise RuntimeLearningError("source provenance is duplicated")
        seen_sources.add(source_digest)
        _integer(source["observations"], "source observations", 1, MAX_COUNTER)
        _integer(source["last_seen"], "source sequence", 0, MAX_COUNTER)
    observed_at = provenance.get("last_observation_at")
    if observed_at is not None and (not isinstance(observed_at, str) or len(observed_at) > 64):
        raise RuntimeLearningError("source observation timestamp differs")
    costs = _mapping(value.get("optimizer_cost"))
    if set(costs) != {"terminal_updates", "replay_updates", "maintenance_updates", "total_updates", "deferred_replay_updates", "rollbacks"}:
        raise RuntimeLearningError("optimizer cost fields differ")
    for name in ("terminal_updates", "replay_updates", "maintenance_updates", "total_updates", "deferred_replay_updates", "rollbacks"):
        _integer(costs.get(name), name, 0, MAX_COUNTER)
    validate_optimizer_checkpoint(value.get("last_healthy"))
    rollback = value.get("last_rollback")
    if rollback is not None:
        if not isinstance(rollback, dict) or set(rollback) != {"reason", "checkpoint_digest", "at_observation"}:
            raise RuntimeLearningError("optimizer rollback metadata differs")
        if not isinstance(rollback["reason"], str) or len(rollback["reason"]) > 192:
            raise RuntimeLearningError("optimizer rollback reason differs")
        _sha(rollback["checkpoint_digest"], "rollback checkpoint digest")
        _integer(rollback["at_observation"], "rollback observation", 0, MAX_COUNTER)
    operator = value.get("last_operator_action")
    if operator is not None:
        if not isinstance(operator, dict) or set(operator) != {"action", "at_observation"}:
            raise RuntimeLearningError("operator checkpoint metadata differs")
        if not isinstance(operator["action"], str) or operator["action"] not in {"import", "reset", "maintenance_recovery"}:
            raise RuntimeLearningError("operator checkpoint action differs")
        _integer(operator["at_observation"], "operator action observation", 0, MAX_COUNTER)
    recovery = value.get("recovery")
    if recovery is not None:
        if not isinstance(recovery, dict) or set(recovery) != {"prior_quarantine", "recovered_at"} or not isinstance(recovery["recovered_at"], str) or len(recovery["recovered_at"]) > 64:
            raise RuntimeLearningError("optimizer recovery metadata differs")
        prior = recovery["prior_quarantine"]
        if prior is not None:
            if not isinstance(prior, dict) or set(prior) != {"reason", "prior_digest"} or not isinstance(prior["reason"], str) or len(prior["reason"]) > 192:
                raise RuntimeLearningError("optimizer recovery quarantine differs")
            _sha(prior["prior_digest"], "prior quarantine digest", allow_empty=True)
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


def _increment(mapping: dict[str, Any], key: str, amount: int = 1) -> None:
    mapping[key] = min(MAX_COUNTER, int(mapping.get(key, 0)) + amount)


def _record_provenance(state: dict[str, Any], observation: Mapping[str, Any]) -> None:
    provenance = state["provenance"]
    partition = _sha(observation.get("partition_id"), "partition_id")
    model = _sha(observation.get("model_selection_digest"), "model_selection_digest")
    source = _sha(observation.get("source_snapshot_digest"), "source_snapshot_digest")
    if provenance["partition_id"] not in {"", partition} or provenance["model_selection_digest"] not in {"", model}:
        raise RuntimeLearningError("optimizer activation/partition provenance differs")
    previous_source = provenance["latest_source_digest"]
    if previous_source and previous_source != source:
        _increment(provenance, "source_switches")
    provenance.update({"partition_id": partition, "model_selection_digest": model,
        "latest_source_digest": source, "last_observation_at": observation.get("observed_at")})
    sources = provenance["recent_sources"]
    selected = next((item for item in sources if item["digest"] == source), None)
    if selected is None:
        if len(sources) >= MAX_RECENT_SOURCES:
            sources.remove(min(sources, key=lambda item: (item["last_seen"], item["digest"])))
        selected = {"digest": source, "observations": 0, "last_seen": 0}
        sources.append(selected)
    _increment(selected, "observations")
    selected["last_seen"] = state["lifetime_observations"]


def _record_prequential(state: dict[str, Any], prediction: Sequence[float], targets: Sequence[float], policy: Mapping[str, Any]) -> None:
    """Update only from predictions made before this outcome enters SGD/replay."""
    absolute = [abs(predicted - target) for predicted, target in zip(prediction, targets, strict=True)]
    squared = [value * value for value in absolute]
    loss = sum(squared) / 3.0
    stats = state["prequential"]
    _increment(stats, "count")
    count = stats["count"]
    difference = loss - stats["mean_loss"]
    stats["mean_loss"] += difference / count
    stats["m2_loss"] = min(MAX_COUNTER, max(0.0, stats["m2_loss"] + difference * (loss - stats["mean_loss"])))
    for name, values in (("absolute_error_mean", absolute), ("squared_error_mean", squared)):
        stats[name] = [previous + (value - previous) / count for previous, value in zip(stats[name], values, strict=True)]
    old_slow = stats["slow_loss"]
    if count == 1:
        stats["fast_loss"] = stats["slow_loss"] = loss
    else:
        stats["fast_loss"] = 0.85 * stats["fast_loss"] + 0.15 * loss
        stats["slow_loss"] = 0.99 * old_slow + 0.01 * loss
    stats["last_loss"] = loss
    stats["recent_losses"] = [*stats["recent_losses"], loss][-MAX_RECENT_LOSSES:]
    stats["drift_debt"] = min(100.0, max(0.0, stats["drift_debt"] + loss - old_slow - 0.02))
    excess = max(0.0, stats["fast_loss"] - stats["slow_loss"] - 0.02)
    stats["drift_score"] = min(1.0, excess * 4.0 + stats["drift_debt"] / 1.5)
    minimum = max(16, int(policy["min_samples"]))
    if count >= minimum and not stats["drift_active"] and excess >= 0.06 and stats["drift_debt"] >= 0.6:
        stats.update({"drift_active": True, "cooldown_remaining": minimum,
            "stable_observations": 0, "last_drift_observation": state["lifetime_observations"], "drift_debt": 0.0})
        _increment(stats, "drift_events")
        # Rebase the detector, while withholding advice until fresh stable
        # outcomes demonstrate adaptation to the changed operating conditions.
        stats["slow_loss"] = max(stats["slow_loss"], stats["fast_loss"])
    elif stats["drift_active"]:
        if loss <= stats["slow_loss"] + 0.05 and excess <= 0.06:
            _increment(stats, "stable_observations")
            stats["cooldown_remaining"] = max(0, stats["cooldown_remaining"] - 1)
        else:
            stats["stable_observations"] = 0
            stats["cooldown_remaining"] = min(minimum, stats["cooldown_remaining"] + 1)
        if stats["cooldown_remaining"] == 0 and stats["stable_observations"] >= minimum:
            stats["drift_active"] = False
            stats["drift_debt"] = 0.0
    state["residual_ema"] = [0.95 * previous + 0.05 * value for previous, value in zip(state["residual_ema"], squared, strict=True)]


def restore_last_healthy(state: dict[str, Any], *, reason: str, policy: Mapping[str, Any]) -> dict[str, Any]:
    """Restore numeric controller weights without changing result/grant state."""
    checkpoint = validate_optimizer_checkpoint(state.get("last_healthy"))
    state["weights"] = list(checkpoint["weights"])
    state["optimizer"] = copy.deepcopy(checkpoint["optimizer"])
    state["quarantined"], state["quarantine"] = False, None
    state["fresh_observations"] = 0
    state["idle_replay_budget"] = 0
    state["prequential"] = _new_prequential()
    state["prequential"].update({"drift_active": True, "cooldown_remaining": max(16, policy["min_samples"])})
    _increment(state, "generation")
    _increment(state["optimizer_cost"], "rollbacks")
    state["last_rollback"] = {"reason": reason[:192], "checkpoint_digest": checkpoint["checkpoint_digest"],
        "at_observation": state["lifetime_observations"]}
    validate_state(state)
    return state


def recover_last_healthy(value: object, *, seed: str, policy: Mapping[str, Any], reason: str) -> dict[str, Any]:
    """Recover only independently hashed finite optimizer data from bad state."""
    if not isinstance(value, dict):
        raise RuntimeLearningError("invalid state has no healthy checkpoint")
    if value.get("schema_version") != SCHEMA or value.get("feature_schema") != FEATURE_SCHEMA or value.get("architecture") != [12, 16, 8, 3] or value.get("controller_version") != CONTROLLER_VERSION:
        raise RuntimeLearningError("healthy recovery feature/controller binding differs")
    checkpoint = validate_optimizer_checkpoint(value.get("last_healthy"))
    recovered = new_state(seed)
    recovered["last_healthy"] = copy.deepcopy(checkpoint)
    recovered["observations"] = checkpoint["observations"]
    lifetime = value.get("lifetime_observations", value.get("observations", checkpoint["observations"]))
    try:
        recovered["lifetime_observations"] = _integer(lifetime, "lifetime observations", checkpoint["observations"], MAX_COUNTER)
    except RuntimeLearningError:
        recovered["lifetime_observations"] = checkpoint["observations"]
    return restore_last_healthy(recovered, reason=reason, policy=policy)


def reset_confidence(state: dict[str, Any], *, reason: str, policy: Mapping[str, Any]) -> dict[str, Any]:
    """An operator checkpoint is a candidate until new canonical outcomes arrive."""
    validate_state(state)
    upgrade_state(state)
    state["fresh_observations"] = 0
    state["idle_replay_budget"] = 0
    state["prequential"] = _new_prequential()
    state["prequential"].update({"drift_active": True, "cooldown_remaining": max(16, policy["min_samples"])})
    state["residual_ema"] = [0.25, 0.25, 0.25]
    _increment(state, "generation")
    state["last_operator_action"] = {"action": reason[:64], "at_observation": state["lifetime_observations"]}
    return state


def checkpoint_envelope(identity: Mapping[str, Any], state: dict[str, Any], *, state_version: int) -> dict[str, Any]:
    validate_state(state)
    upgrade_state(state)
    checkpoint = {
        "schema_version": CHECKPOINT_SCHEMA, "tenant_id": identity["tenant_id"], "scope_id": identity["scope_id"],
        "partition_id": identity["partition_id"], "task_class": identity["task_class"],
        "model_selection_digest": identity["model_selection_digest"], "feature_schema": FEATURE_SCHEMA,
        "state_version": state_version, "state_digest": digest(state),
        "source_snapshot_digest": state["provenance"]["latest_source_digest"], "state": copy.deepcopy(state),
    }
    checkpoint["checkpoint_digest"] = digest(checkpoint)
    return validate_checkpoint_envelope(checkpoint)


def validate_checkpoint_envelope(value: object) -> dict[str, Any]:
    fields = {"schema_version", "tenant_id", "scope_id", "partition_id", "task_class", "model_selection_digest",
        "feature_schema", "state_version", "state_digest", "source_snapshot_digest", "state", "checkpoint_digest"}
    if not isinstance(value, dict) or set(value) != fields or len(canonical(value).encode()) > MAX_CHECKPOINT_BYTES:
        raise RuntimeLearningError("learning checkpoint fields/storage bound differ")
    if value["schema_version"] != CHECKPOINT_SCHEMA or value["feature_schema"] != FEATURE_SCHEMA:
        raise RuntimeLearningError("learning checkpoint schema differs")
    identifier(value["tenant_id"], "tenant_id", maximum=512)
    identifier(value["scope_id"], "scope_id")
    identifier(value["task_class"], "task_class", maximum=256)
    _integer(value["state_version"], "state_version", 1, MAX_COUNTER)
    _sha(value["model_selection_digest"], "model_selection_digest")
    _sha(value["source_snapshot_digest"], "source_snapshot_digest", allow_empty=True)
    partition = digest({"task_class": value["task_class"], "model_selection_digest": value["model_selection_digest"]})
    if _sha(value["partition_id"], "partition_id") != partition:
        raise RuntimeLearningError("learning checkpoint partition binding differs")
    state = validate_state(value["state"])
    if state.get("controller_version") != CONTROLLER_VERSION:
        raise RuntimeLearningError("learning checkpoint controller version differs")
    provenance = state["provenance"]
    if provenance["partition_id"] != partition or provenance["model_selection_digest"] != value["model_selection_digest"] or provenance["latest_source_digest"] != value["source_snapshot_digest"]:
        raise RuntimeLearningError("learning checkpoint activation/source provenance differs")
    if _sha(value["state_digest"], "state_digest") != digest(state):
        raise RuntimeLearningError("learning checkpoint state digest differs")
    if _sha(value["checkpoint_digest"], "checkpoint_digest") != digest({key: item for key, item in value.items() if key != "checkpoint_digest"}):
        raise RuntimeLearningError("learning checkpoint envelope digest differs")
    return value


def _replay_sample(state: Mapping[str, Any], index: int, *, recent_only: bool = False) -> Mapping[str, Any] | None:
    recent = state.get("recent_replay", [])
    historical = state.get("replay", [])
    pool = recent if recent_only or (index % 2 == 0 and recent) else historical
    if not pool:
        pool = recent or historical
    return None if not pool else pool[(int(state["optimizer"]["step"]) + index) % len(pool)]


def learn_outcome(state: dict[str, Any] | None, observation: Mapping[str, Any], policy: Mapping[str, Any], *, seed: str) -> tuple[dict[str, Any], bool]:
    """One canonical sample plus at most three replay updates, deterministically."""
    policy = normalize_policy(policy)
    if state is None:
        state = new_state(seed)
    try:
        validate_state(state)
    except RuntimeLearningError as exc:
        try:
            return recover_last_healthy(state, seed=seed, policy=policy, reason=f"invalid_state:{type(exc).__name__}"), False
        except RuntimeLearningError:
            pass
        try:
            prior_digest = digest(state)
        except RuntimeLearningError:
            prior_digest = ""
        return quarantine_state(seed, reason=str(exc), prior_digest=prior_digest), False
    upgrade_state(state)
    recent_capacity = int(policy["replay_capacity"]) // 2
    historical_capacity = int(policy["replay_capacity"]) - recent_capacity
    state["replay"] = state["replay"][-historical_capacity:]
    state["recent_replay"] = state["recent_replay"][-recent_capacity:]
    if state["quarantined"] or not policy["enabled"] or observation.get("trainable") is not True:
        return state, False
    sample = {
        "outcome_id": identifier(observation.get("outcome_id"), "outcome_id", maximum=64),
        "features": _vector(observation.get("features"), 12, "features", 0.0, 1.0),
        "targets": observation_targets(observation, policy),
    }
    prediction = _forward(state["weights"], sample["features"])[-1]
    _increment(state, "observations")
    _increment(state, "lifetime_observations")
    _increment(state, "fresh_observations")
    _record_provenance(state, observation)
    _record_prequential(state, prediction, sample["targets"], policy)
    costs = state["optimizer_cost"]
    _optimize(state, sample, policy)
    _increment(costs, "terminal_updates")
    _increment(costs, "total_updates")
    replay = state["replay"]
    requested_replays = min(int(policy["replay_steps"]), len(replay) + len(state["recent_replay"]))
    replay_steps = 0 if sample["features"][8] >= policy["pressure_threshold"] else min(1 if state["prequential"]["drift_active"] else 3, requested_replays)
    _increment(costs, "deferred_replay_updates", requested_replays - replay_steps)
    state["idle_replay_budget"] = min(3, int(state["idle_replay_budget"]) + requested_replays - replay_steps)
    for index in range(replay_steps):
        replay_sample = _replay_sample(state, index, recent_only=state["prequential"]["drift_active"])
        if replay_sample is not None:
            _optimize(state, replay_sample, policy)
            _increment(costs, "replay_updates")
            _increment(costs, "total_updates")
    if len(replay) < historical_capacity:
        replay.append(sample)
    else:
        # Deterministic reservoir: old failures are not erased by a recent streak.
        slot = int(sample["outcome_id"][:16], 16) % state["observations"]
        if slot < len(replay):
            replay[slot] = sample
    state["recent_replay"] = [*state["recent_replay"], sample][-recent_capacity:]
    try:
        validate_state(state)
        checkpoint = state["last_healthy"]
        if state["fresh_observations"] >= policy["min_samples"] and not state["prequential"]["drift_active"] and state["prequential"]["fast_loss"] <= state["prequential"]["slow_loss"] + 0.03 and state["observations"] - checkpoint["observations"] >= 32:
            state["last_healthy"] = _optimizer_checkpoint(state)
    except RuntimeLearningError as exc:
        try:
            return restore_last_healthy(state, reason=f"invalid_update:{type(exc).__name__}", policy=policy), False
        except RuntimeLearningError:
            return quarantine_state(seed, reason=str(exc)), False
    return state, True


def replay_maintenance(state: dict[str, Any], policy: Mapping[str, Any], *, max_updates: int = 2) -> dict[str, Any]:
    """Bounded idle optimization; does not invent samples or observed outcomes."""
    policy = normalize_policy(policy)
    validate_state(state)
    upgrade_state(state)
    max_updates = _integer(max_updates, "max_updates", 0, 4)
    if policy["enabled"] and not state["quarantined"]:
        for index in range(min(max_updates, state["idle_replay_budget"], len(state["replay"]) + len(state["recent_replay"]))):
            sample = _replay_sample(state, index, recent_only=state["prequential"]["drift_active"])
            if sample is not None:
                _optimize(state, sample, policy)
                _increment(state["optimizer_cost"], "maintenance_updates")
                _increment(state["optimizer_cost"], "total_updates")
                state["idle_replay_budget"] -= 1
    validate_state(state)
    return state


def state_readiness(state: Mapping[str, Any], policy: Mapping[str, Any], *, source_snapshot_digest: str | None = None) -> dict[str, Any]:
    state = upgrade_state(state if isinstance(state, dict) else dict(state))
    samples = int(state.get("observations", 0))
    fresh_samples = state["fresh_observations"]
    residual = _vector(state.get("residual_ema"), 3, "residual_ema", 0.0, 1.0)
    stats = state["prequential"]
    provenance = state["provenance"]
    source = source_snapshot_digest or provenance["latest_source_digest"]
    known_source = next((item for item in provenance["recent_sources"] if item["digest"] == source), None)
    novelty_penalty = 0.1 if source and known_source is None else 0.0
    variance = stats["m2_loss"] / max(1, stats["count"] - 1)
    uncertainty = min(1.0, math.sqrt(max(sum(residual) / 3.0, stats["fast_loss"]))
        + 1.0 / math.sqrt(fresh_samples + 1.0)
        + min(0.15, 2.0 * math.sqrt(variance / max(1, stats["count"])))
        + (0.25 if stats["drift_active"] else 0.0) + novelty_penalty)
    quarantined = state.get("quarantined") is True
    reasons = []
    if not policy["enabled"]:
        reasons.append("learning_disabled")
    if quarantined:
        reasons.append("optimizer_quarantined")
    if fresh_samples < policy["min_samples"]:
        reasons.append("fresh_samples_required")
    if stats["drift_active"]:
        reasons.append("drift_active")
    if novelty_penalty:
        reasons.append("source_novelty")
    if uncertainty > policy["uncertainty_ceiling"]:
        reasons.append("uncertainty_above_policy")
    readiness = "disabled" if not policy["enabled"] else "quarantined" if quarantined else "ready" if fresh_samples >= policy["min_samples"] and not stats["drift_active"] and uncertainty <= policy["uncertainty_ceiling"] else "cold_start"
    checkpoint = state["last_healthy"]
    return {"samples": samples, "optimizer_steps": int(_mapping(state.get("optimizer")).get("step", 0)),
            "readiness": readiness, "quarantined": quarantined, "uncertainty": uncertainty,
            "prediction_error": math.sqrt(sum(residual) / 3.0), "fresh_samples": fresh_samples,
            "lifetime_samples": state["lifetime_observations"], "confidence_reasons": reasons,
            "generation": state["generation"], "rollback_count": state["optimizer_cost"]["rollbacks"],
            "last_rollback": state["last_rollback"],
            "last_healthy": {"available": True, "observations": checkpoint["observations"],
                "optimizer_step": checkpoint["optimizer"]["step"], "checkpoint_digest": checkpoint["checkpoint_digest"]},
            "drift": {"active": stats["drift_active"], "score": stats["drift_score"], "events": stats["drift_events"],
                "cooldown_remaining": stats["cooldown_remaining"], "fast_loss": stats["fast_loss"],
                "slow_loss": stats["slow_loss"], "last_prequential_loss": stats["last_loss"], "prequential_count": stats["count"]},
            "prequential": {"mean_squared_loss": stats["mean_loss"], "absolute_error_mean": stats["absolute_error_mean"],
                "squared_error_mean": stats["squared_error_mean"], "recent_losses": stats["recent_losses"]},
            "source_provenance": {"latest_source_digest": provenance["latest_source_digest"],
                "requested_source_digest": source, "source_known": known_source is not None,
                "latest_source_samples": 0 if known_source is None else known_source["observations"],
                "recent_source_count": len(provenance["recent_sources"]), "source_switches": provenance["source_switches"]},
            "optimizer_cost": dict(state["optimizer_cost"]),
            "deferred_replay_budget": state["idle_replay_budget"],
            "replay_samples": len(state["replay"]) + len(state["recent_replay"])}


def recommend(state: dict[str, Any] | None, policy: Mapping[str, Any], features: list[float], *, allowed_rounds: int = 1, requested_rounds: int = 1, pressure: float = 0.0, source_snapshot_digest: str | None = None) -> dict[str, Any]:
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
        result.update(state_readiness(state, policy, source_snapshot_digest=source_snapshot_digest))
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
