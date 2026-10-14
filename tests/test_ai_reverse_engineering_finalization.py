from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.bundle_verifier import (
    BundleItem,
    verify_bundle,
)
from skeleton.ai.research.model_internals.reverse_engineering.campaign_audit import (
    AuditCheck,
    audit_campaign,
)
from skeleton.ai.research.model_internals.reverse_engineering.claim_closure import (
    ClaimClosureEvidence,
    evaluate_claim_closure,
)
from skeleton.ai.research.model_internals.reverse_engineering.hierarchical_calibration import (
    GroupCalibrationPrediction,
    analyze_hierarchical_calibration,
)
from skeleton.ai.research.model_internals.reverse_engineering.replication_decay import (
    AgedReplication,
    analyze_replication_decay,
)
from skeleton.ai.research.model_internals.reverse_engineering.transport_stress import (
    TransportStressPoint,
    analyze_transport_stress,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_hierarchical_calibration_surfaces_worst_group():
    report = analyze_hierarchical_calibration(
        (
            GroupCalibrationPrediction("a", "g1", 0.9, True),
            GroupCalibrationPrediction("b", "g1", 0.8, True),
            GroupCalibrationPrediction("c", "g2", 0.9, False),
            GroupCalibrationPrediction("d", "g2", 0.8, False),
        )
    )
    assert report.worst_group_id == "g2"
    assert report.worst_group_gap > 0.8


def test_transport_stress_detects_gap_threshold_crossing():
    probe = d("probe")
    report = analyze_transport_stress(
        (
            TransportStressPoint("a", probe, 0.0, 1.0, 0.95),
            TransportStressPoint("b", probe, 0.5, 1.0, 0.7),
            TransportStressPoint("c", probe, 1.0, 1.0, 0.2),
        ),
        gap_tolerance=0.2,
    )
    assert report.first_gap_above_tolerance == 0.5
    assert report.gap_growth > 0.7


def test_replication_decay_downweights_old_replications():
    claim = d("claim")
    report = analyze_replication_decay(
        (
            AgedReplication("a", claim, 1.0, 0, 0),
            AgedReplication("b", claim, 1.0, 0, 100),
        ),
        half_life_epochs=100.0,
    )
    assert report.mean_raw_quality == 1.0
    assert report.mean_decayed_quality < 1.0
    assert report.minimum_decayed_quality < 0.51


def test_bundle_verifier_detects_tampering_cycle():
    items = (
        BundleItem("a", "evidence", d("a")),
        BundleItem("b", "claim", d("b"), ("a",)),
    )
    assert verify_bundle(items).valid is True
    cyclic = (
        replace(items[0], dependency_ids=("b",)),
        items[1],
    )
    report = verify_bundle(cyclic)
    assert report.cycle_free is False
    assert report.valid is False


def test_claim_closure_requires_every_governance_gate():
    decision = evaluate_claim_closure(
        ClaimClosureEvidence(
            claim_id="c1",
            claim_digest=d("claim"),
            quality_gate_passed=True,
            quorum_met=True,
            lineage_closed=True,
            falsification_status="survived",
            replication_quality=0.9,
            stale_evidence_ratio=0.0,
            contradiction_weight=0.1,
        )
    )
    assert decision.closed is True
    assert decision.failed_requirements == ()


def test_campaign_audit_blocks_critical_failure():
    report = audit_campaign(
        (
            AuditCheck("a", "lineage", True, True),
            AuditCheck("b", "security", False, True),
            AuditCheck("c", "coverage", False, False),
        )
    )
    assert report.readiness == "blocked"
    assert report.critical_failure_count == 1
    assert report.failed_categories == ("coverage", "security")
