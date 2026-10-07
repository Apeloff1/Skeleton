from __future__ import annotations

import pytest

from skeleton.jeeves.historical_independence import (
    CohortDeclaration,
    CohortOverlap,
    HistoricalEvidenceIndependenceAuditor,
    HistoricalIndependenceError,
    IndependencePolicy,
    summarize_independence,
)
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    SelectionPolicy,
    make_benchmark_provenance,
)


NOW = 1_000.0
REASON = BenchmarkDefinition("ind-reason", "v1", BenchmarkDomain.REASONING, 0.0, 100.0)
CODE = BenchmarkDefinition("ind-code", "v1", BenchmarkDomain.CODING, 0.0, 100.0)
MODEL = ModelIdentity("provider", "candidate", "r1")


def _snapshot(snapshot_id: str, benchmark: BenchmarkDefinition, score: float, measured_at: float) -> BenchmarkSnapshot:
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=measured_at,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=MODEL,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
    )
    return BenchmarkSnapshot(
        snapshot_id=snapshot_id,
        model=MODEL,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
        measured_at=measured_at,
        provenance=provenance,
    )


def _decision():
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("reason-a", REASON, 90.0, 800.0))
    registry.ingest(_snapshot("reason-b", REASON, 91.0, 850.0))
    registry.ingest(_snapshot("code-a", CODE, 88.0, 820.0))
    return registry.select_champion(
        SelectionPolicy(
            domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.CODING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
            minimum_sample_count=1,
            confidence_z=0.0,
        )
    )


def test_independent_declared_populations_pass() -> None:
    decision = _decision()
    auditor = HistoricalEvidenceIndependenceAuditor(
        cohorts=[
            CohortDeclaration("c1", frozenset({"reason-a"}), "population-a", 100),
            CohortDeclaration("c2", frozenset({"reason-b"}), "population-b", 100),
            CohortDeclaration("c3", frozenset({"code-a"}), "population-c", 100),
        ],
        policy=IndependencePolicy(min_independent_cohorts=2),
    )
    report = auditor.audit(decision)
    assert report.passed
    assert report.independent_population_count == 3
    assert report.max_observed_overlap == 0.0


def test_duplicate_population_fingerprint_fails_even_with_distinct_snapshot_ids() -> None:
    decision = _decision()
    auditor = HistoricalEvidenceIndependenceAuditor(
        cohorts=[
            CohortDeclaration("run-a", frozenset({"reason-a"}), "same-people", 100),
            CohortDeclaration("run-b", frozenset({"reason-b"}), "same-people", 100),
            CohortDeclaration("code", frozenset({"code-a"}), "other-people", 100),
        ]
    )
    report = auditor.audit(decision)
    assert not report.passed
    assert any(item.finding_id == "duplicate_population" for item in report.findings)
    assert report.max_observed_overlap == 1.0


def test_explicit_excessive_overlap_fails() -> None:
    decision = _decision()
    auditor = HistoricalEvidenceIndependenceAuditor(
        cohorts=[
            CohortDeclaration("c1", frozenset({"reason-a"}), "p1", 100),
            CohortDeclaration("c2", frozenset({"reason-b"}), "p2", 100),
            CohortDeclaration("c3", frozenset({"code-a"}), "p3", 100),
        ],
        overlaps=[CohortOverlap("c1", "c2", 0.75)],
        policy=IndependencePolicy(max_pairwise_overlap=0.20),
    )
    report = auditor.audit(decision)
    assert not report.passed
    assert report.max_observed_overlap == pytest.approx(0.75)
    assert any(item.finding_id == "excessive_pairwise_overlap" for item in report.findings)


def test_overlap_at_threshold_is_allowed() -> None:
    decision = _decision()
    auditor = HistoricalEvidenceIndependenceAuditor(
        cohorts=[
            CohortDeclaration("c1", frozenset({"reason-a"}), "p1", 100),
            CohortDeclaration("c2", frozenset({"reason-b"}), "p2", 100),
            CohortDeclaration("c3", frozenset({"code-a"}), "p3", 100),
        ],
        overlaps=[CohortOverlap("c1", "c2", 0.20)],
        policy=IndependencePolicy(max_pairwise_overlap=0.20),
    )
    assert auditor.audit(decision).passed


def test_undeclared_used_snapshot_fails_closed() -> None:
    decision = _decision()
    auditor = HistoricalEvidenceIndependenceAuditor(
        cohorts=[
            CohortDeclaration("c1", frozenset({"reason-a"}), "p1", 100),
            CohortDeclaration("c2", frozenset({"code-a"}), "p2", 100),
        ],
        policy=IndependencePolicy(min_independent_cohorts=2),
    )
    report = auditor.audit(decision)
    assert not report.passed
    assert report.undeclared_snapshot_ids == ("reason-b",)
    assert any(item.finding_id == "undeclared_snapshots" for item in report.findings)


def test_undeclared_can_be_observed_without_blocking_when_policy_allows() -> None:
    decision = _decision()
    auditor = HistoricalEvidenceIndependenceAuditor(
        cohorts=[
            CohortDeclaration("c1", frozenset({"reason-a"}), "p1", 100),
            CohortDeclaration("c2", frozenset({"code-a"}), "p2", 100),
        ],
        policy=IndependencePolicy(
            min_independent_cohorts=2,
            require_all_snapshots_declared=False,
        ),
    )
    report = auditor.audit(decision)
    assert report.passed
    assert report.undeclared_snapshot_ids == ("reason-b",)


def test_insufficient_independent_population_count_fails() -> None:
    decision = _decision()
    auditor = HistoricalEvidenceIndependenceAuditor(
        cohorts=[
            CohortDeclaration("all", frozenset({"reason-a", "reason-b", "code-a"}), "one-population", 100),
        ],
        policy=IndependencePolicy(min_independent_cohorts=2),
    )
    report = auditor.audit(decision)
    assert not report.passed
    assert any(item.finding_id == "insufficient_independent_cohorts" for item in report.findings)


def test_snapshot_cannot_belong_to_multiple_cohorts() -> None:
    with pytest.raises(HistoricalIndependenceError):
        HistoricalEvidenceIndependenceAuditor(
            cohorts=[
                CohortDeclaration("c1", frozenset({"reason-a"}), "p1", 100),
                CohortDeclaration("c2", frozenset({"reason-a"}), "p2", 100),
            ]
        )


def test_overlap_must_reference_known_cohorts() -> None:
    with pytest.raises(HistoricalIndependenceError):
        HistoricalEvidenceIndependenceAuditor(
            cohorts=[CohortDeclaration("c1", frozenset({"reason-a"}), "p1", 100)],
            overlaps=[CohortOverlap("c1", "missing", 0.1)],
        )


def test_duplicate_overlap_declaration_is_rejected_symmetrically() -> None:
    with pytest.raises(HistoricalIndependenceError):
        HistoricalEvidenceIndependenceAuditor(
            cohorts=[
                CohortDeclaration("c1", frozenset({"reason-a"}), "p1", 100),
                CohortDeclaration("c2", frozenset({"reason-b"}), "p2", 100),
            ],
            overlaps=[CohortOverlap("c1", "c2", 0.1), CohortOverlap("c2", "c1", 0.1)],
        )


def test_declaration_fingerprint_is_order_independent() -> None:
    left = HistoricalEvidenceIndependenceAuditor(
        cohorts=[
            CohortDeclaration("c1", frozenset({"reason-a"}), "p1", 100),
            CohortDeclaration("c2", frozenset({"reason-b"}), "p2", 100),
        ],
        overlaps=[CohortOverlap("c1", "c2", 0.1)],
    )
    right = HistoricalEvidenceIndependenceAuditor(
        cohorts=[
            CohortDeclaration("c2", frozenset({"reason-b"}), "p2", 100),
            CohortDeclaration("c1", frozenset({"reason-a"}), "p1", 100),
        ],
        overlaps=[CohortOverlap("c2", "c1", 0.1)],
    )
    assert left.declaration_fingerprint == right.declaration_fingerprint


def test_summary_is_json_friendly() -> None:
    decision = _decision()
    auditor = HistoricalEvidenceIndependenceAuditor(
        cohorts=[
            CohortDeclaration("c1", frozenset({"reason-a"}), "p1", 100),
            CohortDeclaration("c2", frozenset({"reason-b"}), "p2", 100),
            CohortDeclaration("c3", frozenset({"code-a"}), "p3", 100),
        ]
    )
    report = auditor.audit(decision)
    summary = summarize_independence(report)
    assert summary["passed"] is True
    assert summary["used_snapshot_count"] == 3
    assert summary["report_fingerprint"] == report.report_fingerprint