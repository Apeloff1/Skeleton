from __future__ import annotations

import pytest

from skeleton.jeeves.historical_evaluation import BenchmarkSuite, HoldoutWindow
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    make_benchmark_provenance,
)
from skeleton.jeeves.historical_portfolio import (
    HistoricalExpertPortfolioBuilder,
    HistoricalPortfolioError,
    PortfolioPolicy,
    summarize_portfolio,
)


NOW = 1_000.0
REASON = BenchmarkDefinition("reason-portfolio", "v1", BenchmarkDomain.REASONING, 0.0, 100.0)
CODE = BenchmarkDefinition("code-portfolio", "v1", BenchmarkDomain.CODING, 0.0, 100.0)
SUITE = BenchmarkSuite(
    suite_id="portfolio",
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


def _fixture():
    general = ModelIdentity("provider", "general", "r1")
    reasoner = ModelIdentity("provider", "reasoner", "r1")
    coder = ModelIdentity("provider", "coder", "r1")
    incomplete = ModelIdentity("provider", "incomplete", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    scores = {
        general: (86.0, 86.0),
        reasoner: (94.0, 72.0),
        coder: (75.0, 96.0),
    }
    for model, (reason, code) in scores.items():
        registry.ingest(_snapshot(f"{model.model}-r", model, REASON, reason))
        registry.ingest(_snapshot(f"{model.model}-c", model, CODE, code))
    registry.ingest(_snapshot("incomplete-r", incomplete, REASON, 99.0))
    return registry, general, reasoner, coder, incomplete


def test_portfolio_keeps_general_fallback_and_material_specialists() -> None:
    registry, general, reasoner, coder, _ = _fixture()
    portfolio = HistoricalExpertPortfolioBuilder(
        registry=registry,
        suite=SUITE,
        window=WINDOW,
        policy=PortfolioPolicy(max_models=3, min_specialist_margin=0.05),
    ).build(models=[general, reasoner, coder])

    assert portfolio.fallback_model == general
    assert portfolio.model_for(BenchmarkDomain.REASONING) == reasoner
    assert portfolio.model_for(BenchmarkDomain.CODING) == coder
    assert set(portfolio.specialist_domains) == {BenchmarkDomain.REASONING, BenchmarkDomain.CODING}


def test_specialist_margin_prevents_small_switches() -> None:
    registry, general, reasoner, coder, _ = _fixture()
    portfolio = HistoricalExpertPortfolioBuilder(
        registry=registry,
        suite=SUITE,
        window=WINDOW,
        policy=PortfolioPolicy(max_models=3, min_specialist_margin=0.20),
    ).build(models=[general, reasoner, coder])

    assert portfolio.model_for(BenchmarkDomain.REASONING) == general
    assert portfolio.model_for(BenchmarkDomain.CODING) == general
    assert portfolio.specialist_domains == ()


def test_model_budget_caps_specialist_count() -> None:
    registry, general, reasoner, coder, _ = _fixture()
    portfolio = HistoricalExpertPortfolioBuilder(
        registry=registry,
        suite=SUITE,
        window=WINDOW,
        policy=PortfolioPolicy(max_models=2, min_specialist_margin=0.05),
    ).build(models=[general, reasoner, coder])

    assert len(portfolio.models) == 2
    assert portfolio.fallback_model in portfolio.models
    assert len(portfolio.specialist_domains) == 1


def test_incomplete_models_are_skipped() -> None:
    registry, general, _, _, incomplete = _fixture()
    portfolio = HistoricalExpertPortfolioBuilder(
        registry=registry,
        suite=SUITE,
        window=WINDOW,
    ).build(models=[general, incomplete])
    assert incomplete in portfolio.skipped_models
    assert portfolio.fallback_model == general


def test_unknown_domain_routes_to_fallback() -> None:
    registry, general, reasoner, coder, _ = _fixture()
    portfolio = HistoricalExpertPortfolioBuilder(
        registry=registry,
        suite=SUITE,
        window=WINDOW,
    ).build(models=[general, reasoner, coder])
    assert portfolio.model_for(BenchmarkDomain.RESEARCH) == general


def test_empty_model_scope_fails_closed() -> None:
    registry, *_ = _fixture()
    with pytest.raises(HistoricalPortfolioError) as exc:
        HistoricalExpertPortfolioBuilder(
            registry=registry,
            suite=SUITE,
            window=WINDOW,
        ).build(models=[])
    assert exc.value.context["reason"] == "empty_models"


def test_all_incomplete_models_fail_closed() -> None:
    registry, _, _, _, incomplete = _fixture()
    with pytest.raises(HistoricalPortfolioError) as exc:
        HistoricalExpertPortfolioBuilder(
            registry=registry,
            suite=SUITE,
            window=WINDOW,
        ).build(models=[incomplete])
    assert exc.value.context["reason"] == "no_evaluable_models"


def test_portfolio_fingerprint_is_deterministic() -> None:
    registry, general, reasoner, coder, _ = _fixture()
    builder = HistoricalExpertPortfolioBuilder(registry=registry, suite=SUITE, window=WINDOW)
    first = builder.build(models=[general, reasoner, coder])
    second = builder.build(models=[coder, general, reasoner])
    assert first.portfolio_fingerprint == second.portfolio_fingerprint


def test_summary_exposes_specialist_assignments() -> None:
    registry, general, reasoner, coder, _ = _fixture()
    portfolio = HistoricalExpertPortfolioBuilder(
        registry=registry,
        suite=SUITE,
        window=WINDOW,
        policy=PortfolioPolicy(min_specialist_margin=0.05),
    ).build(models=[general, reasoner, coder])
    summary = summarize_portfolio(portfolio)
    assert summary["fallback_model"] == general.key
    assert BenchmarkDomain.REASONING.value in summary["specialist_domains"]
    assert summary["assignments"]
    assert summary["portfolio_fingerprint"] == portfolio.portfolio_fingerprint