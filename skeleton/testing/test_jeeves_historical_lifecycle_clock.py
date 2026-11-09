from __future__ import annotations

from skeleton.jeeves.historical_evaluation import (
    BenchmarkSuite,
    HistoricalPromotionGate,
    HoldoutWindow,
    PromotionPolicy,
)
from skeleton.jeeves.historical_governance import HistoricalChampionLedger
from skeleton.jeeves.historical_lifecycle import HistoricalModelLifecycle
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


NOW = 8_000_000.0


class FakeProvider:
    name = "fixture"
    supports_system_prompt = True

    def available(self) -> bool:
        return True

    def complete(self, prompt: str, context=None, max_tokens: int = 512, system=None) -> str:
        return prompt


def test_reviewed_proposal_survives_clock_movement_when_evidence_is_unchanged() -> None:
    clock = [NOW]
    model = ModelIdentity("provider", "candidate", "r1")
    benchmark = BenchmarkDefinition(
        benchmark_id="reasoning-clock",
        revision="v1",
        domain=BenchmarkDomain.REASONING,
        raw_min=0.0,
        raw_max=100.0,
    )
    registry = HistoricalModelRegistry(clock=lambda: clock[0])
    measured_at = NOW - 10.0
    provenance = make_benchmark_provenance(
        source_id="fixture:clock",
        source_kind="benchmark",
        measured_at=measured_at,
        clock_version=1,
        snapshot_id="clock-snapshot",
        model=model,
        benchmark=benchmark,
        raw_score=90.0,
        sample_count=100,
    )
    registry.ingest(
        BenchmarkSnapshot(
            snapshot_id="clock-snapshot",
            model=model,
            benchmark=benchmark,
            raw_score=90.0,
            sample_count=100,
            measured_at=measured_at,
            provenance=provenance,
        )
    )

    catalog = ProviderCatalog()
    provider = FakeProvider()
    catalog.bind(model, lambda: provider)
    router = HistoricalChampionRouter(
        registry=registry,
        policy=SelectionPolicy(
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING}),
            minimum_sample_count=1,
            confidence_z=0.0,
            max_snapshot_age_seconds=1_000.0,
        ),
        catalog=catalog,
    )
    promotion_gate = HistoricalPromotionGate(
        registry=registry,
        suite=BenchmarkSuite(
            suite_id="clock-suite",
            revision="v1",
            benchmark_keys=frozenset({benchmark.key}),
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING}),
        ),
        window=HoldoutWindow(NOW - 100.0, NOW + 100.0),
        policy=PromotionPolicy(
            min_holdout_samples=1,
            min_coverage=1.0,
            min_promotion_margin=0.0,
            max_domain_regression=1.0,
            max_volatility=1.0,
            max_latest_drop=1.0,
        ),
    )
    lifecycle = HistoricalModelLifecycle(
        router=router,
        promotion_gate=promotion_gate,
        ledger=HistoricalChampionLedger(clock=lambda: clock[0]),
        catalog=catalog,
        require_activation_authorization=False,
    )

    proposal = lifecycle.propose()
    first_fingerprint = proposal.fingerprint

    clock[0] += 30.0
    refreshed = lifecycle.propose()

    assert refreshed.ranking.evaluated_at != proposal.ranking.evaluated_at
    assert refreshed.fingerprint == first_fingerprint

    activation = lifecycle.activate(proposal)
    assert activation.state.model == model
    assert activation.route.provider is provider