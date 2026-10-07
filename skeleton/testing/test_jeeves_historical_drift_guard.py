from __future__ import annotations

import pytest

from skeleton.jeeves.historical_drift_guard import (
    HistoricalDriftGuardError,
    LineageAwarePromotionGuard,
    summarize_lineage_promotion_review,
)
from skeleton.jeeves.historical_evaluation import (
    BenchmarkSuite,
    HistoricalPromotionGate,
    HoldoutWindow,
    PromotionPolicy,
)
from skeleton.jeeves.historical_governance import HistoricalChampionLedger
from skeleton.jeeves.historical_lifecycle import HistoricalLifecycleError, HistoricalModelLifecycle
from skeleton.jeeves.historical_lineage import DriftPolicy, GenerationDriftAnalyzer, LineageNode, ModelLineage
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    SelectionPolicy,
    make_benchmark_provenance,
)
from skeleton.jeeves.historical_routing import HistoricalChampionRouter, ProviderCatalog


NOW = 1_000.0
REASON = BenchmarkDefinition("guard-reason", "v1", BenchmarkDomain.REASONING, 0.0, 100.0)
CODE = BenchmarkDefinition("guard-code", "v1", BenchmarkDomain.CODING, 0.0, 100.0)
SUITE = BenchmarkSuite(
    suite_id="guard-suite",
    revision="v1",
    benchmark_keys=frozenset({REASON.key, CODE.key}),
    domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.CODING: 1.0},
    required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
)
WINDOW = HoldoutWindow(100.0, 200.0)


class FakeProvider:
    supports_system_prompt = True

    def __init__(self, name: str) -> None:
        self.name = name

    def available(self) -> bool:
        return True

    def complete(self, prompt: str, context=None, max_tokens: int = 512, system=None) -> str:
        return f"{self.name}:{prompt}"


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


def _fixture(*, child_scores=(92.0, 92.0), parent_scores=(85.0, 85.0)):
    parent = ModelIdentity("provider", "model", "r1")
    child = ModelIdentity("provider", "model", "r2")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    for model, scores, prefix in [
        (parent, parent_scores, "p"),
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
            min_promotion_margin=0.01,
            max_domain_regression=1.0,
            max_volatility=1.0,
            max_latest_drop=1.0,
        ),
    )
    lineage = ModelLineage()
    lineage.register(LineageNode(parent, "family", 1))
    lineage.register(LineageNode(child, "family", 2, parent))
    analyzer = GenerationDriftAnalyzer(
        lineage=lineage,
        gate=gate,
        policy=DriftPolicy(material_delta=0.01, severe_regression=0.05, max_regressed_domains=0),
    )
    guard = LineageAwarePromotionGuard(promotion_gate=gate, drift_analyzer=analyzer)
    return registry, gate, lineage, guard, parent, child


def test_first_activation_can_pass_without_lineage_parent() -> None:
    _, gate, _, guard, parent, _ = _fixture()
    promotion = gate.decide(candidate=parent, incumbent=None)
    review = guard.review(candidate=parent, incumbent=None, base_promotion=promotion)
    assert review.allowed is True
    assert review.drift is None
    assert review.reasons == ()


def test_direct_child_without_structural_break_is_allowed() -> None:
    _, gate, _, guard, parent, child = _fixture()
    promotion = gate.decide(candidate=child, incumbent=parent)
    assert promotion.promotable is True
    review = guard.review(candidate=child, incumbent=parent, base_promotion=promotion)
    assert review.allowed is True
    assert review.drift is not None
    assert review.drift.structural_break is False


def test_structural_break_vetoes_aggregate_promotion() -> None:
    _, gate, _, guard, parent, child = _fixture(
        parent_scores=(90.0, 70.0),
        child_scores=(80.0, 95.0),
    )
    promotion = gate.decide(candidate=child, incumbent=parent)
    assert promotion.promotable is True
    review = guard.review(candidate=child, incumbent=parent, base_promotion=promotion)
    assert review.allowed is False
    assert review.drift is not None
    assert review.drift.structural_break is True
    assert "generation_structural_break" in review.reasons


def test_non_direct_child_is_held_when_direct_lineage_required() -> None:
    registry, gate, lineage, _, parent, child = _fixture()
    grandchild = ModelIdentity("provider", "model", "r3")
    lineage.register(LineageNode(grandchild, "family", 3, child))
    registry.ingest(_snapshot("g-r", grandchild, REASON, 95.0))
    registry.ingest(_snapshot("g-c", grandchild, CODE, 95.0))
    analyzer = GenerationDriftAnalyzer(lineage=lineage, gate=gate)
    guard = LineageAwarePromotionGuard(promotion_gate=gate, drift_analyzer=analyzer)
    promotion = gate.decide(candidate=grandchild, incumbent=parent)
    review = guard.review(candidate=grandchild, incumbent=parent, base_promotion=promotion)
    assert review.allowed is False
    assert "not_direct_lineage_child" in review.reasons


def test_missing_lineage_is_held_when_required() -> None:
    registry, gate, lineage, _, parent, _ = _fixture()
    outsider = ModelIdentity("provider", "outsider", "r1")
    registry.ingest(_snapshot("o-r", outsider, REASON, 99.0))
    registry.ingest(_snapshot("o-c", outsider, CODE, 99.0))
    guard = LineageAwarePromotionGuard(
        promotion_gate=gate,
        drift_analyzer=GenerationDriftAnalyzer(lineage=lineage, gate=gate),
    )
    review = guard.review(
        candidate=outsider,
        incumbent=parent,
        base_promotion=gate.decide(candidate=outsider, incumbent=parent),
    )
    assert review.allowed is False
    assert "lineage_unavailable" in review.reasons


def test_base_promotion_hold_remains_a_hold() -> None:
    _, gate, _, guard, parent, child = _fixture(child_scores=(85.2, 85.2))
    promotion = gate.decide(candidate=child, incumbent=parent)
    assert promotion.promotable is False
    review = guard.review(candidate=child, incumbent=parent, base_promotion=promotion)
    assert review.allowed is False
    assert "base_promotion_held" in review.reasons


def test_review_rejects_mismatched_base_decision() -> None:
    _, gate, _, guard, parent, child = _fixture()
    parent_promotion = gate.decide(candidate=parent, incumbent=None)
    with pytest.raises(HistoricalDriftGuardError):
        guard.review(candidate=child, incumbent=parent, base_promotion=parent_promotion)


def test_review_summary_exposes_structural_break() -> None:
    _, gate, _, guard, parent, child = _fixture(
        parent_scores=(90.0, 70.0),
        child_scores=(80.0, 95.0),
    )
    review = guard.review(
        candidate=child,
        incumbent=parent,
        base_promotion=gate.decide(candidate=child, incumbent=parent),
    )
    summary = summarize_lineage_promotion_review(review)
    assert summary["allowed"] is False
    assert summary["structural_break"] is True
    assert summary["review_fingerprint"] == review.review_fingerprint


def test_lifecycle_blocks_structural_break_activation_end_to_end() -> None:
    registry, gate, _, guard, parent, child = _fixture(
        parent_scores=(90.0, 70.0),
        child_scores=(80.0, 95.0),
    )
    catalog = ProviderCatalog()
    catalog.bind(parent, lambda: FakeProvider("parent"))
    catalog.bind(child, lambda: FakeProvider("child"))
    router = HistoricalChampionRouter(
        registry=registry,
        policy=SelectionPolicy(
            domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.CODING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
            minimum_sample_count=1,
            confidence_z=0.0,
            max_snapshot_age_seconds=10_000.0,
        ),
        catalog=catalog,
    )
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    first = gate.decide(candidate=parent, incumbent=None)
    ledger.activate(first)
    lifecycle = HistoricalModelLifecycle(
        router=router,
        promotion_gate=gate,
        ledger=ledger,
        catalog=catalog,
        lineage_guard=guard,
        require_activation_authorization=False,
    )

    proposal = lifecycle.propose(models=[child])

    assert proposal.promotion.promotable is True
    assert proposal.lineage_review is not None
    assert proposal.lineage_review.allowed is False
    assert proposal.promotable is False
    assert "generation_structural_break" in proposal.hold_reasons
    with pytest.raises(HistoricalLifecycleError) as exc:
        lifecycle.activate(proposal)
    assert exc.value.context["reason"] == "proposal_not_promotable"