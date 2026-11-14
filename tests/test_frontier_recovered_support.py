"""Recovered runtime support contract qualification."""
import pytest

from skeleton.frontier.execution import ExecutionPolicy
from skeleton.frontier.health import HealthReport, HealthState, evaluate_health
from skeleton.frontier.payloads import json_snapshot, memory_payload


def test_health_reports_cannot_forge_success_or_mutate_evidence():
    data = {"native": True, "device": False}
    report = evaluate_health(data)
    data["device"] = True
    assert report.state is HealthState.DEGRADED
    assert not report.healthy
    with pytest.raises(TypeError):
        report.checks["device"] = True
    with pytest.raises(ValueError):
        HealthReport(HealthState.HEALTHY, {"native": False})
    with pytest.raises(ValueError):
        evaluate_health({"native": "success"})
    assert evaluate_health({}).state is HealthState.UNAVAILABLE


def test_payload_detaches_state_and_requires_valid_identity():
    item = {"nested": [1, {"key": "value"}]}
    snapshot = memory_payload(item, "record", 4096)
    item["nested"][1]["key"] = "changed"
    assert snapshot["nested"][1]["key"] == "value"
    assert snapshot["id"] == "record"
    with pytest.raises(ValueError):
        memory_payload({"id": "other"}, "record", 4096)
    with pytest.raises(ValueError):
        memory_payload([], "record", 4096)


def test_payload_and_execution_limits_are_finite():
    with pytest.raises(ValueError):
        json_snapshot({"a": "b"}, max_bytes=2)
    with pytest.raises(ValueError):
        json_snapshot({}, max_bytes=9_000_000)
    with pytest.raises(ValueError):
        json_snapshot({"a": float("nan")})
    with pytest.raises(ValueError):
        ExecutionPolicy(max_attempts=11)
    with pytest.raises(ValueError):
        ExecutionPolicy(execution_timeout=float("inf"))
    policy = ExecutionPolicy(retry_delay=0.05, max_retry_delay=1.0)
    assert policy.backoff(1000) == 1.0
