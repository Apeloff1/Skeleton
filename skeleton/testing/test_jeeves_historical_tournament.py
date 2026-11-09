from __future__ import annotations

import pytest

from skeleton.jeeves.historical_evaluation import BenchmarkSuite, HoldoutWindow, PromotionPolicy
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    make_benchmark_provenance,
)
from skeleton.jeeves.historical_tournament import (
    HistoricalChallengerTournament,
    HistoricalTournamentError,
    summarize_tournament,
)


NOW = 1_000.0
REASON = BenchmarkDefinition("reason-tournament", "v1", BenchmarkDomain.REASONING, 0.0, 100.0)
CODE = BenchmarkDefinition("code-tournament", "v1", BenchmarkDomain.CODING, 0.0, 100.0)
SUITE = BenchmarkSuite(
    suite_id="tournament",
    revision="v1",
    benchmark_keys=frozenset({REASON.key, CODE.key}),
    domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.CODING: 1.0},
    required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
)
WINDOW = HoldoutWindow(100.0, 200.0)
POLICY = PromotionPolicy(
    min_holdout_samples=64,
    min_coverage=1.0,
    min_promotion_margin=0.01,
    max_domain_regression=0.02,
    max_volatility=0.08,
    max_latest_drop=0.05,
)


def _snapshot(
    snapshot_id: str,
    model: ModelIdentity,
    benchmark: BenchmarkDefinition,
    score: float,
    *,
    at: float = 150.0,
) -> BenchmarkSnapshot:
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=at,
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
        measured_at=at,
        provenance=provenance,
    )


def _registry():
    incumbent = ModelIdentity("provider", "incumbent", "r1")
    balanced = ModelIdentity("provider", "balanced", "r1")
    tradeoff = ModelIdentity("provider", "tradeoff", "r1")
    incomplete = ModelIdentity("provider", "incomplete", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    for model, reason, code in (
        (incumbent, 80.0, 80.0),
        (balanced, 85.0, 82.0),
        (tradeoff, 90.0, 70.0),
    ):
        registry.ingest(_snapshot(f"{model.model}-reason", model, REASON, reason))
        registry.ingest(_snapshot(f"{model.model}-code", model, CODE, code))
    registry.ingest(_snapshot("incomplete-reason", incomplete, REASON, 99.0))
    return registry, incumbent, balanced, tradeoff, incomplete


def _tournament(registry: HistoricalModelRegistry) -> HistoricalChallengerTournament:
    return HistoricalChallengerTournament(
        registry=registry,
        suite=SUITE,
        window=WINDOW,
        policy=POLICY,
    )


def test_balanced_challenger_can_promote_and_dominate_incumbent() -> None:
    registry, incumbent, balanced, _, _ = _registry()
    report = _tournament(registry).run(incumbent=incumbent, challengers=[balanced])
    result = report.challengers[0]
    assert result.model == balanced
    assert result.promotable is True
    assert result.dominates_incumbent is True
    assert result.aggregate_delta == pytest.approx(0.035)
    assert all(delta.delta >= 0.0 for delta in result.domain_deltas)


def test_aggregate_tie_with_domain_regression_is_held() -> None:
    registry, incumbent, _, tradeoff, _ = _registry()
    report = _tournament(registry).run(incumbent=incumbent, challengers=[tradeoff])
    result = report.challengers[0]
    assert result.promotable is False
    assert "domain_regression:coding" in result.decision.reasons
    assert "insufficient_promotion_margin" in result.decision.reasons
    assert result.dominates_incumbent is False


def test_incomplete_challenger_is_skipped() -> None:
    registry, incumbent, balanced, _, incomplete = _registry()
    report = _tournament(registry).run(
        incumbent=incumbent,
        challengers=[balanced, incomplete],
    )
    assert incomplete in report.skipped_models
    assert [result.model for result in report.challengers] == [balanced]


def test_pareto_frontier_keeps_tradeoff_and_dominating_balanced_model() -> None:
    registry, incumbent, balanced, tradeoff, _ = _registry()
    report = _tournament(registry).run(
        incumbent=incumbent,
        challengers=[balanced, tradeoff],
    )
    assert balanced in report.pareto_frontier
    assert tradeoff in report.pareto_frontier
    assert incumbent not in report.pareto_frontier


def test_promotable_challengers_are_ordered_before_held_challengers() -> None:
    registry, incumbent, balanced, tradeoff, _ = _registry()
    report = _tournament(registry).run(
        incumbent=incumbent,
        challengers=[tradeoff, balanced],
    )
    assert report.challengers[0].model == balanced
    assert report.challengers[0].promotable is True
    assert report.challengers[1].model == tradeoff
    assert report.challengers[1].promotable is False


def test_incumbent_must_have_complete_holdout_evidence() -> None:
    registry, _, balanced, _, incomplete = _registry()
    with pytest.raises(HistoricalTournamentError) as exc:
        _tournament(registry).run(incumbent=incomplete, challengers=[balanced])
    assert exc.value.context["reason"] == "incumbent_missing_required_domain"


def test_tournament_requires_distinct_challenger() -> None:
    registry, incumbent, _, _, _ = _registry()
    with pytest.raises(HistoricalTournamentError) as exc:
        _tournament(registry).run(incumbent=incumbent, challengers=[incumbent])
    assert exc.value.context["reason"] == "empty_challengers"


def test_all_incomplete_challengers_fail_closed() -> None:
    registry, incumbent, _, _, incomplete = _registry()
    with pytest.raises(HistoricalTournamentError) as exc:
        _tournament(registry).run(incumbent=incumbent, challengers=[incomplete])
    assert exc.value.context["reason"] == "no_evaluable_challengers"


def test_report_fingerprint_is_deterministic_across_challenger_input_order() -> None:
    registry, incumbent, balanced, tradeoff, _ = _registry()
    first = _tournament(registry).run(incumbent=incumbent, challengers=[balanced, tradeoff])
    second = _tournament(registry).run(incumbent=incumbent, challengers=[tradeoff, balanced])
    assert first.report_fingerprint == second.report_fingerprint


def test_summary_exposes_frontier_deltas_and_promotion_state() -> None:
    registry, incumbent, balanced, tradeoff, incomplete = _registry()
    report = _tournament(registry).run(
        incumbent=incumbent,
        challengers=[balanced, tradeoff, incomplete],
    )
    summary = summarize_tournament(report)
    assert summary["incumbent"] == incumbent.key
    assert balanced.key in summary["promotable_challengers"]
    assert incomplete.key in summary["skipped_models"]
    assert summary["challengers"][0]["domain_deltas"]
    assert summary["report_fingerprint"] == report.report_fingerprint
