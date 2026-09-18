from __future__ import annotations

import pytest

from skeleton.jeeves.historical_evaluation import (
    BenchmarkSuite,
    HistoricalPromotionGate,
    HoldoutWindow,
    PromotionPolicy,
)
from skeleton.jeeves.historical_lineage import (
    DriftDirection,
    DriftPolicy,
    GenerationDriftAnalyzer,
    HistoricalLineageError,
    LineageNode,
    ModelLineage,
    summarize_drift,
)
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    make_benchmark_provenance,
)


NOW = 1_000.0
REASON = BenchmarkDefinition("lineage-reason", "v1", BenchmarkDomain.REASONING, 0.0, 100.0)
CODE = BenchmarkDefinition("lineage-code", "v1", BenchmarkDomain.CODING, 0.0, 100.0)
SUITE = BenchmarkSuite(
    suite_id="lineage-suite",
    revision="v1",
    benchmark_keys=frozenset({REASON.key, CODE.key}),
    domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.CODING: 1.0},
    required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
)
WINDOW = HoldoutWindow(100.0, 200.0)


def _snapshot(snapshot_id, model, benchmark, score):
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=150.0,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
    )
    return BenchmarkSnapshot(
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
        measured_at=150.0,
        provenance=provenance,
    )


def _fixture(child_scores=(88.0, 90.0)):
    parent = ModelIdentity("provider", "jeeves-model", "r1")
    child = ModelIdentity("provider", "jeeves-model", "r2")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    for model, scores, prefix in [
        (parent, (84.0, 86.0), "p"),
        (child, child_scores, "c"),
    ]:
        registry.ingest(_snapshot(f"{prefix}-r", model, REASON, scores[0]))
        registry.ingest(_snapshot(f"{prefix}-c", model, CODE, scores[1]))
    gate = HistoricalPromotionGate(
        registry=registry,
        suite=SUITE,
        window=WINDOW,
        policy=PromotionPolicy(
            min_holdout_samples=1,
            min_coverage=1.0,
            min_promotion_margin=0.0,
            max_domain_regression=1.0,
            max_volatility=1.0,
            max_latest_drop=1.0,
        ),
    )
    lineage = ModelLineage()
    lineage.register(LineageNode(parent, "jeeves-family", 1))
    lineage.register(LineageNode(child, "jeeves-family", 2, parent))
    return lineage, gate, parent, child


def test_lineage_requires_root_generation_one() -> None:
    lineage = ModelLineage()
    model = ModelIdentity("provider", "m", "r1")
    with pytest.raises(HistoricalLineageError):
        lineage.register(LineageNode(model, "family", 2))


def test_child_requires_existing_parent() -> None:
    lineage = ModelLineage()
    parent = ModelIdentity("provider", "m", "r1")
    child = ModelIdentity("provider", "m", "r2")
    with pytest.raises(HistoricalLineageError):
        lineage.register(LineageNode(child, "family", 2, parent))


def test_child_generation_must_increment_exactly_one() -> None:
    lineage = ModelLineage()
    parent = ModelIdentity("provider", "m", "r1")
    child = ModelIdentity("provider", "m", "r3")
    lineage.register(LineageNode(parent, "family", 1))
    with pytest.raises(HistoricalLineageError):
        lineage.register(LineageNode(child, "family", 3, parent))


def test_provider_change_is_not_silently_treated_as_same_lineage() -> None:
    lineage = ModelLineage()
    parent = ModelIdentity("provider-a", "m", "r1")
    child = ModelIdentity("provider-b", "m", "r2")
    lineage.register(LineageNode(parent, "family", 1))
    with pytest.raises(HistoricalLineageError):
        lineage.register(LineageNode(child, "family", 2, parent))


def test_duplicate_family_generation_is_rejected() -> None:
    lineage = ModelLineage()
    root = ModelIdentity("provider", "m", "r1")
    a = ModelIdentity("provider", "m-a", "r2")
    b = ModelIdentity("provider", "m-b", "r2")
    lineage.register(LineageNode(root, "family", 1))
    lineage.register(LineageNode(a, "family", 2, root))
    with pytest.raises(HistoricalLineageError):
        lineage.register(LineageNode(b, "family", 2, root))


def test_ancestors_and_latest_are_deterministic() -> None:
    lineage, _, parent, child = _fixture()
    assert lineage.ancestors(child)[0].model == parent
    assert lineage.latest("jeeves-family").model == child
    assert [node.generation for node in lineage.family("jeeves-family")] == [1, 2]


def test_improvements_are_reported_per_domain() -> None:
    lineage, gate, parent, child = _fixture((90.0, 92.0))
    report = GenerationDriftAnalyzer(
        lineage=lineage,
        gate=gate,
        policy=DriftPolicy(material_delta=0.01, severe_regression=0.05, max_regressed_domains=0),
    ).compare(child)

    assert report.parent == parent
    assert report.child == child
    assert report.aggregate_delta == pytest.approx(0.06)
    assert set(report.improved_domains) == {BenchmarkDomain.REASONING, BenchmarkDomain.CODING}
    assert report.regressed_domains == ()
    assert report.structural_break is False
    assert all(item.direction is DriftDirection.IMPROVED for item in report.domains)


def test_small_changes_are_stable() -> None:
    lineage, gate, _, child = _fixture((84.5, 85.5))
    report = GenerationDriftAnalyzer(
        lineage=lineage,
        gate=gate,
        policy=DriftPolicy(material_delta=0.01, severe_regression=0.05, max_regressed_domains=1),
    ).compare(child)
    assert all(item.direction is DriftDirection.STABLE for item in report.domains)


def test_domain_regression_can_trigger_structural_break() -> None:
    lineage, gate, _, child = _fixture((90.0, 80.0))
    report = GenerationDriftAnalyzer(
        lineage=lineage,
        gate=gate,
        policy=DriftPolicy(material_delta=0.01, severe_regression=0.05, max_regressed_domains=0),
    ).compare(child)
    assert report.regressed_domains == (BenchmarkDomain.CODING,)
    assert report.severe_regression is True
    assert report.structural_break is True


def test_non_severe_regression_can_break_domain_budget() -> None:
    lineage, gate, _, child = _fixture((83.0, 85.0))
    report = GenerationDriftAnalyzer(
        lineage=lineage,
        gate=gate,
        policy=DriftPolicy(material_delta=0.005, severe_regression=0.10, max_regressed_domains=0),
    ).compare(child)
    assert report.severe_regression is False
    assert report.regressed_domains == (BenchmarkDomain.REASONING,)
    assert report.structural_break is True


def test_root_cannot_be_compared_to_missing_parent() -> None:
    lineage, gate, parent, _ = _fixture()
    with pytest.raises(HistoricalLineageError):
        GenerationDriftAnalyzer(lineage=lineage, gate=gate).compare(parent)


def test_compare_family_reports_each_transition() -> None:
    lineage, gate, _, child = _fixture()
    grandchild = ModelIdentity("provider", "jeeves-model", "r3")
    lineage.register(LineageNode(grandchild, "jeeves-family", 3, child))
    gate.registry.ingest(_snapshot("g-r", grandchild, REASON, 91.0))
    gate.registry.ingest(_snapshot("g-c", grandchild, CODE, 93.0))
    reports = GenerationDriftAnalyzer(lineage=lineage, gate=gate).compare_family("jeeves-family")
    assert len(reports) == 2
    assert reports[-1].child == grandchild


def test_incomplete_child_holdout_fails_closed() -> None:
    parent = ModelIdentity("provider", "m", "r1")
    child = ModelIdentity("provider", "m", "r2")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("p-r", parent, REASON, 80.0))
    registry.ingest(_snapshot("p-c", parent, CODE, 80.0))
    registry.ingest(_snapshot("c-r", child, REASON, 90.0))
    gate = HistoricalPromotionGate(registry=registry, suite=SUITE, window=WINDOW)
    lineage = ModelLineage()
    lineage.register(LineageNode(parent, "family", 1))
    lineage.register(LineageNode(child, "family", 2, parent))
    with pytest.raises(HistoricalLineageError):
        GenerationDriftAnalyzer(lineage=lineage, gate=gate).compare(child)


def test_lineage_fingerprint_changes_with_new_generation() -> None:
    lineage, _, _, child = _fixture()
    before = lineage.fingerprint
    grandchild = ModelIdentity("provider", "jeeves-model", "r3")
    lineage.register(LineageNode(grandchild, "jeeves-family", 3, child))
    assert lineage.fingerprint != before


def test_summary_exposes_drift_evidence() -> None:
    lineage, gate, _, child = _fixture((90.0, 92.0))
    report = GenerationDriftAnalyzer(lineage=lineage, gate=gate).compare(child)
    summary = summarize_drift(report)
    assert summary["child"] == child.key
    assert summary["report_fingerprint"] == report.report_fingerprint
    assert summary["domains"]