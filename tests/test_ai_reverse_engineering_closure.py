from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.calibration_curve import (
    CalibrationPrediction,
    analyze_calibration_curve,
)
from skeleton.ai.research.model_internals.reverse_engineering.evidence_staleness import (
    EvidenceAge,
    analyze_evidence_staleness,
)
from skeleton.ai.research.model_internals.reverse_engineering.falsification_registry import (
    Falsifier,
    evaluate_falsifiers,
)
from skeleton.ai.research.model_internals.reverse_engineering.lineage_closure import (
    LineageNode,
    analyze_lineage_closure,
)
from skeleton.ai.research.model_internals.reverse_engineering.missingness import (
    MissingnessRecord,
    analyze_missingness,
)
from skeleton.ai.research.model_internals.reverse_engineering.version_drift import (
    VersionSignature,
    analyze_version_drift,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_lineage_closure_requires_replication_for_supported_claim():
    nodes = (
        LineageNode("e", "evidence", d("e")),
        LineageNode("a", "analysis", d("a"), ("e",)),
        LineageNode("c", "claim", d("c"), ("a",)),
        LineageNode("r", "replication", d("r"), ("c",)),
    )
    report = analyze_lineage_closure(nodes, supported_claim_ids=("c",))
    assert report.fully_closed is True
    assert report.closed_claim_count == 1


def test_falsifier_registry_marks_triggered_claim_falsified():
    reports = evaluate_falsifiers(
        (
            Falsifier("f1", "c1", d("desc1"), d("ev1"), False),
            Falsifier("f2", "c1", d("desc2"), d("ev2"), True),
        )
    )
    assert reports[0].status == "falsified"
    assert reports[0].triggered_ids == ("f2",)


def test_calibration_curve_computes_brier_and_gap():
    report = analyze_calibration_curve(
        (
            CalibrationPrediction("a", 0.9, True),
            CalibrationPrediction("b", 0.8, True),
            CalibrationPrediction("c", 0.2, False),
            CalibrationPrediction("d", 0.1, False),
        ),
        bins=4,
    )
    assert report.brier_score < 0.05
    assert report.expected_calibration_error < 0.2


def test_version_drift_accumulates_signature_change():
    report = analyze_version_drift(
        (
            VersionSignature("v1", 1, (("a", 0.0), ("b", 0.0))),
            VersionSignature("v2", 2, (("a", 0.1), ("b", 0.0))),
            VersionSignature("v3", 3, (("a", 0.1), ("b", 0.2))),
        )
    )
    assert report.version_count == 3
    assert report.cumulative_euclidean_distance == 0.30000000000000004
    assert report.maximum_step_distance == 0.2


def test_missingness_reports_complete_ratio():
    report = analyze_missingness(
        (
            MissingnessRecord("a", (("x", False), ("y", False))),
            MissingnessRecord("b", (("x", True), ("y", False))),
        )
    )
    assert report.complete_record_ratio == 0.5
    assert dict(report.missing_rate_by_field)["x"] == 0.5


def test_evidence_staleness_flags_old_items():
    report = analyze_evidence_staleness(
        (
            EvidenceAge("a", d("a"), 1, 5, 10),
            EvidenceAge("b", d("b"), 1, 20, 10),
        )
    )
    assert report.stale_count == 1
    assert report.stale_ids == ("b",)
