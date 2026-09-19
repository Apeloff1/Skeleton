"""Observation policy, metrics, audit export, and provider routing tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.audit_export import AIAuditExporter
from skeleton.shells.ai.calibration import AICalibration
from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.metrics import AIShellMetrics
from skeleton.shells.ai.model_port import CallableAIModelPort, ModelCapabilities
from skeleton.shells.ai.observation import AIObservation
from skeleton.shells.ai.observation_policy import (
    ObservationExposure,
    ObservationPolicy,
    ObservationPolicyEngine,
)
from skeleton.shells.ai.provider_health import ProviderHealthRegistry
from skeleton.shells.ai.provider_router import AIProviderRouter
from skeleton.shells.ai.provenance import AIDecisionProvenance
from skeleton.shells.ai.trust import ModelTrustRegistry


def fp(char):
    return char * 64


def observation(excerpt=""):
    return AIObservation(
        "o",
        "c",
        "python",
        True,
        0,
        False,
        False,
        1.0,
        10,
        0,
        fp("a"),
        fp("b"),
        excerpt,
    )


def test_observation_metadata_only_removes_excerpt():
    engine = ObservationPolicyEngine(
        ObservationPolicy(exposure=ObservationExposure.METADATA_ONLY)
    )
    data = engine.sanitize(observation("hello"))
    assert data["safe_excerpt"] == ""


def test_observation_digest_only_reduces_surface():
    engine = ObservationPolicyEngine(
        ObservationPolicy(exposure=ObservationExposure.DIGEST_ONLY)
    )
    data = engine.sanitize(observation("hello"))
    assert "duration_ms" not in data
    assert "stdout_digest" in data


def test_observation_redacts_blocked_patterns():
    engine = ObservationPolicyEngine(
        ObservationPolicy(exposure=ObservationExposure.REDACTED_EXCERPT)
    )
    data = engine.sanitize(observation("token secret password"))
    assert "token" not in data["safe_excerpt"].lower()
    assert "secret" not in data["safe_excerpt"].lower()


def test_observation_excerpt_truncated():
    engine = ObservationPolicyEngine(
        ObservationPolicy(
            exposure=ObservationExposure.REDACTED_EXCERPT,
            max_excerpt_chars=4,
            blocked_patterns=(),
        )
    )
    assert engine.sanitize(observation("abcdefgh"))["safe_excerpt"] == "abcd"


def test_metrics_low_cardinality_command_key():
    metrics = AIShellMetrics()
    metrics.planned("python")
    metrics.reviewed("python", risk_score=10)
    metrics.approved("python")
    snapshot = metrics.executed("python", ok=True, verified=True)
    assert snapshot.planning_attempts == 1
    assert snapshot.reviews == 1
    assert snapshot.executions == 1
    assert snapshot.average_risk_score == 10


def test_metrics_verification_failure_distinct():
    metrics = AIShellMetrics()
    item = metrics.executed("python", ok=True, verified=False)
    assert item.execution_failures == 0
    assert item.verification_failures == 1


def provenance():
    return AIDecisionProvenance(
        fp("a"),
        fp("b"),
        fp("c"),
        fp("d"),
        fp("e"),
        fp("f"),
        "m",
        10,
        receipt_root=fp("1"),
    )


def test_audit_export_keeps_allowed_decision_data_only():
    journal = AIDecisionJournal()
    journal.append(
        "ai.plan.completed",
        session_id="s",
        intent_id="i",
        proposal_id="p",
        data={
            "ok": True,
            "duration_ms": 1,
            "raw_output": "SECRET",
        },
    )
    export = AIAuditExporter().export(journal, provenance())
    assert export.events[0]["data"]["ok"] is True
    assert "raw_output" not in export.events[0]["data"]
    assert "SECRET" not in str(export.to_dict())


def test_audit_export_digest_stable():
    journal = AIDecisionJournal()
    export = AIAuditExporter().export(journal, provenance())
    assert len(export.digest) == 64
    assert export.digest == export.digest


def model(model_id, **caps):
    return CallableAIModelPort(
        model_id,
        lambda request: {},
        capabilities=ModelCapabilities(**caps),
    )


def test_provider_router_healthy_before_degraded():
    health = ProviderHealthRegistry()
    health.record_success("healthy", latency_ms=1)
    health.record_failure("degraded")
    router = AIProviderRouter(health)
    routes = router.route(
        (
            model("degraded"),
            model("healthy"),
        )
    )
    assert routes[0].model.model_id == "healthy"


def test_provider_router_quarantined_last():
    health = ProviderHealthRegistry()
    health.quarantine("bad")
    router = AIProviderRouter(health)
    routes = router.route((model("bad"), model("unknown")))
    assert routes[-1].model.model_id == "bad"


def test_provider_router_structured_tool_capability_bonus():
    health = ProviderHealthRegistry()
    router = AIProviderRouter(health)
    weak = model("weak", structured_output=False, tool_use=False)
    strong = model("strong", structured_output=True, tool_use=True)
    routes = router.route((weak, strong))
    assert routes[0].model.model_id == "strong"


def test_provider_router_uses_trust_when_available():
    calibration = AICalibration()
    calibration.record(
        "trusted",
        predicted_confidence=0.9,
        success=True,
        verified=True,
        latency_ms=1,
    )
    trust = ModelTrustRegistry(calibration)
    trust.record_verification("trusted", verified=True)
    health = ProviderHealthRegistry()
    router = AIProviderRouter(health, trust)
    routes = router.route((model("trusted"), model("unknown")))
    assert routes[0].model.model_id == "trusted"
