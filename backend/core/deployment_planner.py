"""Deterministic deployment plan compiler for governed Operations actions.

This does not pretend to deploy. It compiles a validated, attested rollout plan
that a future external executor can consume: preflight gates, staged rollout,
health checks, rollback triggers and immutable input identity.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

_ALLOWED_ENVS = {"development", "staging", "production"}
_ALLOWED_STRATEGIES = {"rolling", "canary", "blue-green"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compile_deployment_plan(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("deployment payload must be an object")
    environment = str(payload.get("environment") or "staging").strip().lower()
    strategy = str(payload.get("strategy") or ("canary" if environment == "production" else "rolling")).strip().lower()
    target = str(payload.get("target") or "product-runtime").strip()
    artifact = str(payload.get("artifact") or payload.get("artifact_id") or "").strip()
    if environment not in _ALLOWED_ENVS:
        raise ValueError("unsupported deployment environment")
    if strategy not in _ALLOWED_STRATEGIES:
        raise ValueError("unsupported deployment strategy")
    if not target:
        raise ValueError("deployment target is required")
    if not artifact:
        raise ValueError("deployment artifact is required")

    production = environment == "production"
    requested_pct = int(payload.get("canary_percent", 5 if production else 100))
    if requested_pct < 1 or requested_pct > 100:
        raise ValueError("canary_percent must be between 1 and 100")
    canary_pct = min(requested_pct, 25) if strategy == "canary" and production else requested_pct

    preflight = [
        "artifact.integrity_verified",
        "policy.assurance_not_blocked",
        "executor.contract_pinned",
        "rollback.artifact_available",
    ]
    if production:
        preflight += ["change.approval_present", "observability.baseline_available"]

    if strategy == "canary":
        phases = [
            {"id": "canary", "traffic_pct": canary_pct, "hold_seconds": 300 if production else 60},
            {"id": "expand", "traffic_pct": 50, "hold_seconds": 600 if production else 120},
            {"id": "full", "traffic_pct": 100, "hold_seconds": 0},
        ]
    elif strategy == "blue-green":
        phases = [
            {"id": "green-warmup", "traffic_pct": 0, "hold_seconds": 180},
            {"id": "green-cutover", "traffic_pct": 100, "hold_seconds": 300 if production else 60},
        ]
    else:
        phases = [
            {"id": "rolling", "traffic_pct": 100, "batch_pct": 10 if production else 25, "hold_seconds": 120 if production else 30},
        ]

    health = {
        "max_error_rate_pct": float(payload.get("max_error_rate_pct", 1.0 if production else 5.0)),
        "max_p95_latency_ms": int(payload.get("max_p95_latency_ms", 750)),
        "min_success_rate_pct": float(payload.get("min_success_rate_pct", 99.0 if production else 95.0)),
    }
    if not (0 <= health["max_error_rate_pct"] <= 100 and 0 <= health["min_success_rate_pct"] <= 100):
        raise ValueError("health percentages must be between 0 and 100")
    if health["max_p95_latency_ms"] <= 0:
        raise ValueError("max_p95_latency_ms must be positive")

    plan = {
        "schema_version": 1,
        "target": target,
        "artifact": artifact,
        "environment": environment,
        "strategy": strategy,
        "preflight": preflight,
        "phases": phases,
        "health": health,
        "rollback": {
            "automatic": True,
            "triggers": ["health.error_rate", "health.latency", "health.success_rate", "operator.abort"],
            "strategy": "restore_previous_verified_artifact",
        },
    }
    plan["plan_sha256"] = hashlib.sha256(_canonical(plan)).hexdigest()
    return plan


def verify_deployment_plan(plan: dict[str, Any]) -> bool:
    candidate = dict(plan)
    digest = str(candidate.pop("plan_sha256", ""))
    return bool(digest) and hashlib.sha256(_canonical(candidate)).hexdigest() == digest
