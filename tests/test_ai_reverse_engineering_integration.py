from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from skeleton.ai.research.model_internals.reverse_engineering.campaign import (
    CampaignArtifact,
    build_campaign_manifest,
)
from skeleton.ai.research.model_internals.reverse_engineering.claim_registry import (
    ClaimRecord,
    ClaimRegistry,
)
from skeleton.ai.research.model_internals.reverse_engineering.contracts import (
    ReverseEngineeringError,
)
from skeleton.ai.research.model_internals.reverse_engineering.drift_alarm import (
    DriftSignal,
    evaluate_drift_alarm,
)
from skeleton.ai.research.model_internals.reverse_engineering.report_export import (
    build_report_envelope,
    verify_report_envelope,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_claim_registry_fails_closed_on_unsupported_promotion():
    registry = ClaimRegistry().add(
        ClaimRecord(
            "claim-1",
            "family:gqa",
            quality_gate_digest=d("gate"),
            quorum_digest=d("quorum"),
            replication_digest=d("replication"),
            evidence_digests=(d("e1"), d("e2")),
        )
    )
    with pytest.raises(ReverseEngineeringError, match="requires quality gate"):
        registry.transition("claim-1", "supported", reason="premature")

    promoted = registry.transition(
        "claim-1",
        "supported",
        reason="all gates passed",
        quality_gate_passed=True,
        quorum_met=True,
        replication_passed=True,
    )
    assert promoted.get("claim-1").status == "supported"
    assert promoted.digest != registry.digest


def test_campaign_manifest_is_order_independent():
    artifacts = (
        CampaignArtifact("evidence", "evidence", d("evidence")),
        CampaignArtifact("claim", "claim", d("claim"), ("evidence",)),
    )
    first = build_campaign_manifest("c", d("protocol"), "target", artifacts)
    second = build_campaign_manifest("c", d("protocol"), "target", tuple(reversed(artifacts)))
    assert first.digest == second.digest


def test_report_envelope_detects_payload_tampering():
    envelope = build_report_envelope("test", d("report"), {"value": 1})
    assert verify_report_envelope(envelope) is True
    tampered = replace(envelope, payload={"value": 2})
    assert verify_report_envelope(tampered) is False


def test_drift_alarm_requires_cross_domain_signal_or_critical_trigger():
    warning = evaluate_drift_alarm(
        (
            DriftSignal("a", "routing", 0.3, 0.1),
            DriftSignal("b", "calibration", 0.2, 0.1),
            DriftSignal("c", "memory", 0.05, 0.1),
        )
    )
    assert warning.severity == "warning"
    assert warning.triggered_domain_count == 2

    critical = evaluate_drift_alarm(
        (DriftSignal("x", "security", 0.2, 0.1, critical=True),)
    )
    assert critical.severity == "critical"
