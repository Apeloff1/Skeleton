from __future__ import annotations

import pytest

from skeleton.jeeves.historical_evaluation import (
    BenchmarkSuite,
    HistoricalPromotionGate,
    HoldoutWindow,
    PromotionPolicy,
)
from skeleton.jeeves.historical_governance import (
    HistoricalChampionLedger,
    HistoricalGovernanceError,
    summarize_champion_state,
)
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    make_benchmark_provenance,
)
from skeleton.jeeves.historical_routing import ProviderCatalog


NOW = 5_000_000.0


class FakeProvider:
    supports_system_prompt = True

    def __init__(self, name: str, available: bool = True) -> None:
        self.name = name
        self._available = available

    def available(self) -> bool:
        return self._available

    def complete(self, prompt: str, context=None, max_tokens: int = 512, system=None) -> str:
        return f"{self.name}:{prompt}"


def _promotion(model: ModelIdentity, score: float = 90.0):
    benchmark = BenchmarkDefinition(
        benchmark_id=f"reason-{model.model}",
        revision="v1",
        domain=BenchmarkDomain.REASONING,
        raw_min=0.0,
        raw_max=100.0,
    )
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{model.key}",
        source_kind="benchmark",
        measured_at=NOW - 10.0,
        clock_version=1,
        snapshot_id=f"snapshot-{model.model}",
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
    )
    registry.ingest(
        BenchmarkSnapshot(
            snapshot_id=f"snapshot-{model.model}",
            model=model,
            benchmark=benchmark,
            raw_score=score,
            sample_count=100,
            measured_at=NOW - 10.0,
            provenance=provenance,
        )
    )
    suite = BenchmarkSuite(
        suite_id="suite",
        revision="v1",
        benchmark_keys=frozenset({benchmark.key}),
        domain_weights={BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
    )
    gate = HistoricalPromotionGate(
        registry=registry,
        suite=suite,
        window=HoldoutWindow(NOW - 100.0, NOW),
        policy=PromotionPolicy(
            min_holdout_samples=1,
            min_coverage=1.0,
            min_promotion_margin=0.0,
            max_domain_regression=1.0,
            max_volatility=1.0,
            max_latest_drop=1.0,
        ),
    )
    return gate.decide(candidate=model)


def _held_decision(model: ModelIdentity):
    benchmark = BenchmarkDefinition(
        benchmark_id="reason-held",
        revision="v1",
        domain=BenchmarkDomain.REASONING,
        raw_min=0.0,
        raw_max=100.0,
    )
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    provenance = make_benchmark_provenance(
        source_id="fixture:held",
        source_kind="benchmark",
        measured_at=NOW - 10.0,
        clock_version=1,
        snapshot_id="held",
        model=model,
        benchmark=benchmark,
        raw_score=90.0,
        sample_count=1,
    )
    registry.ingest(
        BenchmarkSnapshot(
            snapshot_id="held",
            model=model,
            benchmark=benchmark,
            raw_score=90.0,
            sample_count=1,
            measured_at=NOW - 10.0,
            provenance=provenance,
        )
    )
    suite = BenchmarkSuite(
        suite_id="suite-held",
        revision="v1",
        benchmark_keys=frozenset({benchmark.key}),
        domain_weights={BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
    )
    gate = HistoricalPromotionGate(
        registry=registry,
        suite=suite,
        window=HoldoutWindow(NOW - 100.0, NOW),
        policy=PromotionPolicy(min_holdout_samples=64),
    )
    return gate.decide(candidate=model)


def test_first_promotion_activates_candidate() -> None:
    model = ModelIdentity("provider", "a", "r1")
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    state = ledger.activate(_promotion(model))
    assert state.version == 1
    assert state.model == model
    assert state.previous_version is None
    assert ledger.active_model == model


def test_non_promotable_decision_is_rejected() -> None:
    model = ModelIdentity("provider", "held", "r1")
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    with pytest.raises(HistoricalGovernanceError) as exc:
        ledger.activate(_held_decision(model))
    assert exc.value.context["reason"] == "decision_not_promotable"


def test_same_decision_cannot_be_consumed_twice() -> None:
    model = ModelIdentity("provider", "a", "r1")
    decision = _promotion(model)
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    ledger.activate(decision)
    with pytest.raises(HistoricalGovernanceError) as exc:
        ledger.activate(decision)
    assert exc.value.context["reason"] == "duplicate_decision"


def test_already_active_model_is_rejected_even_with_new_decision() -> None:
    model = ModelIdentity("provider", "a", "r1")
    first = _promotion(model, 90.0)
    second = _promotion(model, 91.0)
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    ledger.activate(first)
    with pytest.raises(HistoricalGovernanceError) as exc:
        ledger.activate(second)
    assert exc.value.context["reason"] == "already_active"


def test_new_promotion_links_previous_version() -> None:
    a = ModelIdentity("provider", "a", "r1")
    b = ModelIdentity("provider", "b", "r1")
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    first = ledger.activate(_promotion(a))
    second = ledger.activate(_promotion(b))
    assert first.version == 1
    assert second.version == 2
    assert second.previous_version == 1
    assert ledger.active_model == b


def test_rollback_restores_prior_model_as_new_version() -> None:
    a = ModelIdentity("provider", "a", "r1")
    b = ModelIdentity("provider", "b", "r1")
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    ledger.activate(_promotion(a))
    ledger.activate(_promotion(b))
    rollback = ledger.rollback(1)
    assert rollback.version == 3
    assert rollback.model == a
    assert rollback.rollback_of == 1
    assert rollback.previous_version == 2
    assert ledger.active_model == a


def test_rollback_does_not_mutate_old_states() -> None:
    a = ModelIdentity("provider", "a", "r1")
    b = ModelIdentity("provider", "b", "r1")
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    original = ledger.activate(_promotion(a))
    ledger.activate(_promotion(b))
    ledger.rollback(1)
    assert original.version == 1
    assert original.model == a
    assert original.rollback_of is None


def test_unknown_rollback_target_fails_closed() -> None:
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    with pytest.raises(HistoricalGovernanceError) as exc:
        ledger.rollback(99)
    assert exc.value.context["reason"] == "unknown_or_evicted_version"


def test_cannot_rollback_to_current_active_version() -> None:
    a = ModelIdentity("provider", "a", "r1")
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    state = ledger.activate(_promotion(a))
    with pytest.raises(HistoricalGovernanceError) as exc:
        ledger.rollback(state.version)
    assert exc.value.context["reason"] == "already_active_version"


def test_history_is_bounded_and_evicted_versions_cannot_be_rollback_targets() -> None:
    models = [ModelIdentity("provider", name, "r1") for name in ("a", "b", "c")]
    ledger = HistoricalChampionLedger(clock=lambda: NOW, max_history=2)
    for model in models:
        ledger.activate(_promotion(model))
    assert [state.version for state in ledger.history()] == [2, 3]
    with pytest.raises(HistoricalGovernanceError) as exc:
        ledger.rollback(1)
    assert exc.value.context["reason"] == "unknown_or_evicted_version"


def test_route_active_uses_exact_allowlisted_binding() -> None:
    model = ModelIdentity("provider", "a", "r1")
    provider = FakeProvider("a")
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    state = ledger.activate(_promotion(model))
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: provider)
    route = ledger.route_active(catalog)
    assert route.state == state
    assert route.provider is provider


def test_route_active_requires_an_active_champion() -> None:
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    with pytest.raises(HistoricalGovernanceError) as exc:
        ledger.route_active(ProviderCatalog())
    assert exc.value.context["reason"] == "no_active_champion"


def test_route_active_rejects_unavailable_provider() -> None:
    model = ModelIdentity("provider", "a", "r1")
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    ledger.activate(_promotion(model))
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: FakeProvider("a", available=False))
    with pytest.raises(HistoricalGovernanceError) as exc:
        ledger.route_active(catalog)
    assert exc.value.context["reason"] == "active_provider_unavailable"


def test_state_fingerprint_is_deterministic() -> None:
    model = ModelIdentity("provider", "a", "r1")
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    state = ledger.activate(_promotion(model))
    assert state.fingerprint == state.fingerprint


def test_summary_contains_rollback_lineage_and_fingerprint() -> None:
    a = ModelIdentity("provider", "a", "r1")
    b = ModelIdentity("provider", "b", "r1")
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    ledger.activate(_promotion(a))
    ledger.activate(_promotion(b))
    rollback = ledger.rollback(1)
    summary = summarize_champion_state(rollback)
    assert summary["version"] == 3
    assert summary["model"] == a.key
    assert summary["rollback_of"] == 1
    assert summary["previous_version"] == 2
    assert summary["state_fingerprint"]