from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.ablation_dose_response import (
    DoseResponseTrial,
    analyze_ablation_dose_response,
)
from skeleton.ai.research.model_internals.reverse_engineering.drift_response_policy import (
    DriftPolicySignal,
    decide_drift_response,
)
from skeleton.ai.research.model_internals.reverse_engineering.evidence_confidence import (
    ConfidenceComponent,
    aggregate_evidence_confidence,
)
from skeleton.ai.research.model_internals.reverse_engineering.evidence_ledger import (
    EvidenceLedger,
)
from skeleton.ai.research.model_internals.reverse_engineering.experiment_coverage import (
    CoverageObservation,
    analyze_experiment_coverage,
)
from skeleton.ai.research.model_internals.reverse_engineering.multimodal_intervention import (
    MultimodalInterventionObservation,
    analyze_multimodal_intervention_consistency,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_multimodal_intervention_agrees_across_modalities():
    report = analyze_multimodal_intervention_consistency(
        (
            MultimodalInterventionObservation("a", d("s1"), "text", "steer", 0.0, 0.5),
            MultimodalInterventionObservation("b", d("s1"), "vision", "steer", 0.0, 0.4),
            MultimodalInterventionObservation("c", d("s2"), "text", "steer", 0.0, 0.3),
            MultimodalInterventionObservation("d", d("s2"), "vision", "steer", 0.0, 0.2),
        )
    )[0]
    assert report.modality_count == 2
    assert report.semantic_pair_count == 2
    assert report.sign_agreement_ratio == 1.0


def test_ablation_dose_response_tracks_monotonic_decrease():
    report = analyze_ablation_dose_response(
        (
            DoseResponseTrial("a", d("p"), 0.0, 1.0),
            DoseResponseTrial("b", d("p"), 0.5, 0.7),
            DoseResponseTrial("c", d("p"), 1.0, 0.2),
        )
    )
    assert report.monotonic_direction == "decreasing"
    assert report.monotonicity_violations == 0
    assert report.total_change == -0.8


def test_experiment_coverage_finds_missing_factorial_cell():
    observations = (
        CoverageObservation("a", (("dose", "low"), ("mode", "x")), 1),
        CoverageObservation("b", (("dose", "low"), ("mode", "y")), 1),
        CoverageObservation("c", (("dose", "high"), ("mode", "x")), 1),
    )
    report = analyze_experiment_coverage(
        observations,
        factor_levels={"dose": ("low", "high"), "mode": ("x", "y")},
    )
    assert report.expected_cell_count == 4
    assert report.observed_cell_count == 3
    assert report.missing_cell_count == 1
    assert report.cell_coverage_ratio == 0.75


def test_evidence_ledger_detects_tampering():
    ledger = EvidenceLedger().append(
        event_kind="report",
        subject_id="r1",
        evidence_digest=d("one"),
    ).append(
        event_kind="claim",
        subject_id="c1",
        evidence_digest=d("two"),
    )
    assert ledger.verify() is True
    tampered_entry = replace(ledger.entries[1], subject_id="other")
    tampered = EvidenceLedger((ledger.entries[0], tampered_entry))
    assert tampered.verify() is False


def test_conservative_confidence_uses_mandatory_floor():
    report = aggregate_evidence_confidence(
        (
            ConfidenceComponent("calibration", 0.9, 2.0, True),
            ConfidenceComponent("replication", 0.7, 2.0, True),
            ConfidenceComponent("coverage", 1.0, 1.0, False),
        )
    )
    assert report.mandatory_floor == 0.7
    assert report.conservative_score <= 0.7
    assert report.weakest_component == "replication"


def test_drift_policy_freezes_on_critical_signal():
    decision = decide_drift_response(
        (
            DriftPolicySignal("a", "routing", "observe"),
            DriftPolicySignal("b", "calibration", "critical"),
        )
    )
    assert decision.action == "freeze_and_revalidate"
    assert decision.freezes_claim_promotion is True
    assert decision.requires_revalidation is True
