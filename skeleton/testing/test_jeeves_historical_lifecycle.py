from __future__ import annotations

import pytest

from skeleton.jeeves.historical_evaluation import (
    BenchmarkSuite,
    HistoricalPromotionGate,
    HoldoutWindow,
    PromotionPolicy,
)
from skeleton.jeeves.historical_governance import HistoricalChampionLedger
from skeleton.jeeves.historical_lifecycle import (
    HistoricalLifecycleError,
    HistoricalModelLifecycle,
    summarize_lifecycle_proposal,
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
from skeleton.jeeves.historical_routing import HistoricalChampionRouter, ProviderCatalog


NOW = 6_000_000.0


class FakeProvider:
    supports_system_prompt = True

    def __init__(self, name: str, available: bool = True) -> None:
        self.name = name
        self._available = available

    def available(self) -> bool:
        return self._available

    def complete(self, prompt: str, context=None, max_tokens: int = 512, system=None) -> str:
        return f"{self.name}:{prompt}"


def _definition(name: str) -> BenchmarkDefinition:
    return BenchmarkDefinition(
        benchmark_id=name,
        revision="v1",
        domain=BenchmarkDomain.REASONING,
        raw_min=0.0,
        raw_max=100.0,
    )


def _ingest(
    registry: HistoricalModelRegistry,
    model: ModelIdentity,
    definition: BenchmarkDefinition,
    score: float,
    *,
    snapshot_id: str,
    measured_at: float = NOW - 10.0,
) -> None:
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=measured_at,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=definition,
        raw_score=score,
        sample_count=100,
    )
    registry.ingest(
        BenchmarkSnapshot(
            snapshot_id=snapshot_id,
            model=model,
            benchmark=definition,
            raw_score=score,
            sample_count=100,
            measured_at=measured_at,
            provenance=provenance,
        )
    )


def _lifecycle(
    registry: HistoricalModelRegistry,
    catalog: ProviderCatalog,
    definition: BenchmarkDefinition,
    *,
    ledger: HistoricalChampionLedger | None = None,
    promotion_margin: float = 0.0,
    require_activation_authorization: bool = False,
) -> HistoricalModelLifecycle:
    selection_policy = SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=10_000.0,
    )
    router = HistoricalChampionRouter(
        registry=registry,
        policy=selection_policy,
        catalog=catalog,
    )
    suite = BenchmarkSuite(
        suite_id="suite",
        revision="v1",
        benchmark_keys=frozenset({definition.key}),
        domain_weights={BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
    )
    gate = HistoricalPromotionGate(
        registry=registry,
        suite=suite,
        window=HoldoutWindow(NOW - 1_000.0, NOW),
        policy=PromotionPolicy(
            min_holdout_samples=1,
            min_coverage=1.0,
            min_promotion_margin=promotion_margin,
            max_domain_regression=1.0,
            max_volatility=1.0,
            max_latest_drop=1.0,
        ),
    )
    return HistoricalModelLifecycle(
        router=router,
        promotion_gate=gate,
        ledger=ledger or HistoricalChampionLedger(clock=lambda: NOW),
        catalog=catalog,
        require_activation_authorization=require_activation_authorization,
    )


def test_propose_is_read_only() -> None:
    model = ModelIdentity("provider", "a", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, definition, 90.0, snapshot_id="a")
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: FakeProvider("a"))
    lifecycle = _lifecycle(registry, catalog, definition)

    proposal = lifecycle.propose()

    assert proposal.candidate == model
    assert proposal.promotable is True
    assert lifecycle.ledger.active_model is None


def test_activate_commits_proposal_and_routes_exact_provider() -> None:
    model = ModelIdentity("provider", "a", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, definition, 90.0, snapshot_id="a")
    provider = FakeProvider("a")
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: provider)
    lifecycle = _lifecycle(registry, catalog, definition)

    activation = lifecycle.activate(lifecycle.propose())

    assert activation.state.model == model
    assert activation.route.provider is provider
    assert lifecycle.ledger.active_model == model


def test_default_production_activation_requires_readiness_authorization() -> None:
    model = ModelIdentity("provider", "a", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, definition, 90.0, snapshot_id="a")
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: FakeProvider("a"))
    lifecycle = _lifecycle(
        registry,
        catalog,
        definition,
        require_activation_authorization=True,
    )
    proposal = lifecycle.propose()

    with pytest.raises(HistoricalLifecycleError) as exc:
        lifecycle.activate(proposal)

    assert exc.value.context["reason"] == "activation_authorization_required"
    assert lifecycle.ledger.active_model is None


def test_best_available_historical_candidate_is_proposed() -> None:
    a = ModelIdentity("provider", "a", "r1")
    b = ModelIdentity("provider", "b", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, a, definition, 90.0, snapshot_id="a")
    _ingest(registry, b, definition, 95.0, snapshot_id="b", measured_at=NOW - 20.0)
    catalog = ProviderCatalog()
    catalog.bind(a, lambda: FakeProvider("a"))
    catalog.bind(b, lambda: FakeProvider("b"))

    proposal = _lifecycle(registry, catalog, definition).propose()

    assert proposal.candidate == b


def test_unavailable_stronger_candidate_is_excluded_before_proposal() -> None:
    strong = ModelIdentity("provider", "strong", "r1")
    available = ModelIdentity("provider", "available", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, strong, definition, 99.0, snapshot_id="strong")
    _ingest(registry, available, definition, 85.0, snapshot_id="available", measured_at=NOW - 20.0)
    catalog = ProviderCatalog()
    catalog.bind(strong, lambda: FakeProvider("strong", available=False))
    catalog.bind(available, lambda: FakeProvider("available"))

    proposal = _lifecycle(registry, catalog, definition).propose()

    assert proposal.candidate == available


def test_explicit_candidate_scope_is_preserved() -> None:
    a = ModelIdentity("provider", "a", "r1")
    b = ModelIdentity("provider", "b", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, a, definition, 90.0, snapshot_id="a")
    _ingest(registry, b, definition, 95.0, snapshot_id="b", measured_at=NOW - 20.0)
    catalog = ProviderCatalog()
    catalog.bind(a, lambda: FakeProvider("a"))
    catalog.bind(b, lambda: FakeProvider("b"))
    lifecycle = _lifecycle(registry, catalog, definition)

    proposal = lifecycle.propose(models=[a])

    assert proposal.candidate == a
    assert proposal.candidate_scope == (a,)


def test_held_proposal_cannot_activate() -> None:
    incumbent = ModelIdentity("provider", "incumbent", "r1")
    candidate = ModelIdentity("provider", "candidate", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, incumbent, definition, 90.0, snapshot_id="incumbent")
    _ingest(registry, candidate, definition, 90.5, snapshot_id="candidate", measured_at=NOW - 20.0)
    catalog = ProviderCatalog()
    catalog.bind(incumbent, lambda: FakeProvider("incumbent"))
    catalog.bind(candidate, lambda: FakeProvider("candidate"))
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    bootstrap = _lifecycle(registry, catalog, definition, ledger=ledger)
    bootstrap.activate(bootstrap.propose(models=[incumbent]))
    lifecycle = _lifecycle(registry, catalog, definition, ledger=ledger, promotion_margin=0.01)

    proposal = lifecycle.propose(models=[candidate])

    assert proposal.promotable is False
    with pytest.raises(HistoricalLifecycleError) as exc:
        lifecycle.activate(proposal)
    assert exc.value.context["reason"] == "proposal_not_promotable"


def test_new_evidence_makes_reviewed_proposal_stale() -> None:
    model = ModelIdentity("provider", "a", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, definition, 90.0, snapshot_id="a1", measured_at=NOW - 30.0)
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: FakeProvider("a"))
    lifecycle = _lifecycle(registry, catalog, definition)
    proposal = lifecycle.propose()
    _ingest(registry, model, definition, 91.0, snapshot_id="a2", measured_at=NOW - 20.0)

    with pytest.raises(HistoricalLifecycleError) as exc:
        lifecycle.activate(proposal)
    assert exc.value.context["reason"] == "stale_proposal"


def test_new_stronger_candidate_makes_unscoped_proposal_stale() -> None:
    a = ModelIdentity("provider", "a", "r1")
    b = ModelIdentity("provider", "b", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, a, definition, 90.0, snapshot_id="a")
    catalog = ProviderCatalog()
    catalog.bind(a, lambda: FakeProvider("a"))
    catalog.bind(b, lambda: FakeProvider("b"))
    lifecycle = _lifecycle(registry, catalog, definition)
    proposal = lifecycle.propose()
    _ingest(registry, b, definition, 99.0, snapshot_id="b", measured_at=NOW - 20.0)

    with pytest.raises(HistoricalLifecycleError) as exc:
        lifecycle.activate(proposal)
    assert exc.value.context["reason"] == "stale_proposal"
    assert exc.value.context["current_candidate"] == b.key


def test_incumbent_change_makes_proposal_stale() -> None:
    a = ModelIdentity("provider", "a", "r1")
    b = ModelIdentity("provider", "b", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, a, definition, 90.0, snapshot_id="a")
    _ingest(registry, b, definition, 95.0, snapshot_id="b", measured_at=NOW - 20.0)
    catalog = ProviderCatalog()
    catalog.bind(a, lambda: FakeProvider("a"))
    catalog.bind(b, lambda: FakeProvider("b"))
    ledger = HistoricalChampionLedger(clock=lambda: NOW)
    lifecycle = _lifecycle(registry, catalog, definition, ledger=ledger)
    proposal = lifecycle.propose(models=[b])
    lifecycle.activate(lifecycle.propose(models=[a]))

    with pytest.raises(HistoricalLifecycleError) as exc:
        lifecycle.activate(proposal)
    assert exc.value.context["reason"] == "stale_proposal"


def test_route_active_delegates_to_ledger() -> None:
    model = ModelIdentity("provider", "a", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, definition, 90.0, snapshot_id="a")
    provider = FakeProvider("a")
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: provider)
    lifecycle = _lifecycle(registry, catalog, definition)
    lifecycle.activate(lifecycle.propose())

    route = lifecycle.route_active()

    assert route.state.model == model
    assert route.provider is provider


def test_proposal_fingerprint_is_deterministic_without_state_change() -> None:
    model = ModelIdentity("provider", "a", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, definition, 90.0, snapshot_id="a")
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: FakeProvider("a"))
    lifecycle = _lifecycle(registry, catalog, definition)

    first = lifecycle.propose()
    second = lifecycle.propose()

    assert first.fingerprint == second.fingerprint


def test_summary_contains_rank_validate_lineage() -> None:
    model = ModelIdentity("provider", "a", "r1")
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, definition, 90.0, snapshot_id="a")
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: FakeProvider("a"))

    summary = summarize_lifecycle_proposal(_lifecycle(registry, catalog, definition).propose())

    assert summary["candidate"] == model.key
    assert summary["historical_best_percent"] == 90.0
    assert summary["promotable"] is True
    assert summary["ranking_policy_fingerprint"]
    assert summary["promotion_decision_fingerprint"]
    assert summary["proposal_fingerprint"]


def test_catalog_mismatch_is_rejected() -> None:
    definition = _definition("reason")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    catalog_a = ProviderCatalog()
    catalog_b = ProviderCatalog()
    router = HistoricalChampionRouter(
        registry=registry,
        policy=SelectionPolicy(
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING}),
        ),
        catalog=catalog_a,
    )
    gate = HistoricalPromotionGate(
        registry=registry,
        suite=BenchmarkSuite(
            suite_id="suite",
            revision="v1",
            benchmark_keys=frozenset({definition.key}),
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING}),
        ),
        window=HoldoutWindow(NOW - 100.0, NOW),
    )
    with pytest.raises(HistoricalLifecycleError) as exc:
        HistoricalModelLifecycle(
            router=router,
            promotion_gate=gate,
            ledger=HistoricalChampionLedger(clock=lambda: NOW),
            catalog=catalog_b,
        )
    assert exc.value.context["reason"] == "catalog_mismatch"


def test_registry_mismatch_is_rejected() -> None:
    definition = _definition("reason")
    registry_a = HistoricalModelRegistry(clock=lambda: NOW)
    registry_b = HistoricalModelRegistry(clock=lambda: NOW)
    catalog = ProviderCatalog()
    router = HistoricalChampionRouter(
        registry=registry_a,
        policy=SelectionPolicy(
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING}),
        ),
        catalog=catalog,
    )
    gate = HistoricalPromotionGate(
        registry=registry_b,
        suite=BenchmarkSuite(
            suite_id="suite",
            revision="v1",
            benchmark_keys=frozenset({definition.key}),
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING}),
        ),
        window=HoldoutWindow(NOW - 100.0, NOW),
    )
    with pytest.raises(HistoricalLifecycleError) as exc:
        HistoricalModelLifecycle(
            router=router,
            promotion_gate=gate,
            ledger=HistoricalChampionLedger(clock=lambda: NOW),
            catalog=catalog,
        )
    assert exc.value.context["reason"] == "registry_mismatch"