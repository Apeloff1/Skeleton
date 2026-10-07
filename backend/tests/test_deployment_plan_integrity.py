from __future__ import annotations

import hashlib
import json

import pytest

from core.deployment_planner import compile_deployment_plan, verify_deployment_plan


def _rehash(plan: dict) -> dict:
    forged = dict(plan)
    forged.pop("plan_sha256", None)
    forged["plan_sha256"] = hashlib.sha256(
        json.dumps(forged, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return forged


@pytest.mark.parametrize(
    "payload",
    [
        {"artifact": "sha256:dev", "environment": "development", "strategy": "rolling"},
        {"artifact": "sha256:stage", "environment": "staging", "strategy": "blue-green"},
        {
            "artifact": "sha256:prod",
            "environment": "production",
            "strategy": "canary",
            "canary_percent": 17,
            "max_error_rate_pct": 0.5,
            "max_p95_latency_ms": 400,
            "min_success_rate_pct": 99.5,
        },
    ],
)
def test_compiler_outputs_are_semantically_verified(payload):
    plan = compile_deployment_plan(payload)
    assert verify_deployment_plan(plan) is True


def test_rehashed_unsupported_environment_is_rejected():
    plan = compile_deployment_plan({"artifact": "sha256:a", "environment": "staging"})
    plan["environment"] = "moon"
    assert verify_deployment_plan(_rehash(plan)) is False


def test_rehashed_noncanonical_phase_is_rejected():
    plan = compile_deployment_plan({
        "artifact": "sha256:a",
        "environment": "production",
        "strategy": "canary",
        "canary_percent": 10,
    })
    plan["phases"] = [dict(row) for row in plan["phases"]]
    plan["phases"][1]["traffic_pct"] = 100
    assert verify_deployment_plan(_rehash(plan)) is False


def test_rehashed_weakened_health_gate_is_rejected():
    plan = compile_deployment_plan({"artifact": "sha256:a", "environment": "production"})
    plan["health"] = dict(plan["health"])
    plan["health"]["max_error_rate_pct"] = 101.0
    assert verify_deployment_plan(_rehash(plan)) is False


def test_rehashed_disabled_rollback_is_rejected():
    plan = compile_deployment_plan({"artifact": "sha256:a", "environment": "staging"})
    plan["rollback"] = dict(plan["rollback"])
    plan["rollback"]["automatic"] = False
    assert verify_deployment_plan(_rehash(plan)) is False


def test_rehashed_extra_field_is_rejected():
    plan = compile_deployment_plan({"artifact": "sha256:a", "environment": "staging"})
    plan["operator_override"] = True
    assert verify_deployment_plan(_rehash(plan)) is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_error_rate_pct", float("nan")),
        ("max_error_rate_pct", float("inf")),
        ("min_success_rate_pct", float("-inf")),
        ("max_p95_latency_ms", True),
    ],
)
def test_nonfinite_and_boolean_health_values_fail_closed(field, value):
    plan = compile_deployment_plan({"artifact": "sha256:a", "environment": "staging"})
    plan["health"] = dict(plan["health"])
    plan["health"][field] = value
    assert verify_deployment_plan(_rehash(plan)) is False


def test_digest_only_tamper_is_rejected():
    plan = compile_deployment_plan({"artifact": "sha256:a", "environment": "staging"})
    plan["plan_sha256"] = "0" * 64
    assert verify_deployment_plan(plan) is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("artifact", {"sha256": "a"}, "artifact must be a string"),
        ("target", ["runtime"], "target must be a string"),
        ("environment", ["staging"], "environment must be a string"),
        ("strategy", {"name": "rolling"}, "strategy must be a string"),
        ("canary_percent", True, "canary_percent must be numeric"),
        ("canary_percent", 12.5, "canary_percent must be a whole number"),
        ("max_p95_latency_ms", False, "max_p95_latency_ms must be numeric"),
        ("max_p95_latency_ms", 12.5, "max_p95_latency_ms must be a whole number"),
        ("max_error_rate_pct", float("nan"), "max_error_rate_pct must be finite"),
        ("min_success_rate_pct", float("inf"), "min_success_rate_pct must be finite"),
    ],
)
def test_compiler_rejects_ambiguous_or_nonportable_input(field, value, message):
    payload = {"artifact": "sha256:a", field: value}
    with pytest.raises(ValueError, match=message):
        compile_deployment_plan(payload)


def test_numeric_strings_remain_supported_without_lossy_truncation():
    plan = compile_deployment_plan({
        "artifact": "sha256:a",
        "environment": "production",
        "strategy": "canary",
        "canary_percent": "17",
        "max_error_rate_pct": "0.5",
        "max_p95_latency_ms": "400",
        "min_success_rate_pct": "99.5",
    })
    assert plan["phases"][0]["traffic_pct"] == 17
    assert plan["health"] == {
        "max_error_rate_pct": 0.5,
        "max_p95_latency_ms": 400,
        "min_success_rate_pct": 99.5,
    }
    assert verify_deployment_plan(plan) is True
