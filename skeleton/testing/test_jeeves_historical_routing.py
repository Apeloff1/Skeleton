from __future__ import annotations

import pytest

from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    SelectionPolicy,
    make_benchmark_provenance,
)
from skeleton.jeeves.historical_routing import (
    HistoricalChampionRouter,
    HistoricalRoutingError,
    ProviderBinding,
    ProviderCatalog,
    build_jeeves_from_historical_champion,
    builtin_provider_binding,
)


NOW = 3_000_000.0


class FakeProvider:
    supports_system_prompt = True

    def __init__(self, name: str, *, is_available: bool = True) -> None:
        self.name = name
        self._is_available = is_available
        self.calls: list[str] = []

    def available(self) -> bool:
        return self._is_available

    def complete(self, prompt: str, context=None, max_tokens: int = 512, system=None) -> str:
        self.calls.append(prompt)
        return f"{self.name}:{prompt}"


class InvalidProvider:
    name = "invalid"
    supports_system_prompt = True

    def available(self) -> bool:
        return True


def _policy() -> SelectionPolicy:
    return SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=10_000.0,
    )


def _add_score(
    registry: HistoricalModelRegistry,
    model: ModelIdentity,
    score: float,
    *,
    snapshot_id: str,
) -> None:
    benchmark = BenchmarkDefinition(
        benchmark_id="reasoning-fixture",
        revision="v1",
        domain=BenchmarkDomain.REASONING,
        raw_min=0.0,
        raw_max=100.0,
    )
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=NOW - 10.0,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
    )
    registry.ingest(
        BenchmarkSnapshot(
            snapshot_id=snapshot_id,
            model=model,
            benchmark=benchmark,
            raw_score=score,
            sample_count=100,
            measured_at=NOW - 10.0,
            provenance=provenance,
        )
    )


def test_catalog_rejects_duplicate_identity() -> None:
    model = ModelIdentity("local", "echo", "r1")
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: FakeProvider("one"))
    with pytest.raises(HistoricalRoutingError) as exc:
        catalog.bind(model, lambda: FakeProvider("two"))
    assert exc.value.context["reason"] == "duplicate_binding"


def test_binding_rejects_non_callable_factory() -> None:
    model = ModelIdentity("local", "echo", "r1")
    with pytest.raises(HistoricalRoutingError) as exc:
        ProviderBinding(model=model, factory=None)  # type: ignore[arg-type]
    assert exc.value.context["reason"] == "invalid_factory"


def test_binding_validates_provider_contract() -> None:
    model = ModelIdentity("local", "echo", "r1")
    binding = ProviderBinding(model=model, factory=InvalidProvider)
    with pytest.raises(HistoricalRoutingError) as exc:
        binding.instantiate()
    assert exc.value.context["reason"] == "invalid_provider"


def test_unavailable_provider_is_not_routable() -> None:
    model = ModelIdentity("local", "echo", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _add_score(registry, model, 95.0, snapshot_id="score")
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: FakeProvider("offline", is_available=False))
    router = HistoricalChampionRouter(registry=registry, policy=_policy(), catalog=catalog)
    with pytest.raises(HistoricalRoutingError) as exc:
        router.route()
    assert exc.value.context["reason"] == "no_available_provider"


def test_historical_winner_must_be_allowlisted() -> None:
    stronger = ModelIdentity("provider-a", "strong", "r1")
    weaker = ModelIdentity("provider-b", "trusted", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _add_score(registry, stronger, 99.0, snapshot_id="strong")
    _add_score(registry, weaker, 80.0, snapshot_id="weak")
    catalog = ProviderCatalog()
    trusted_provider = FakeProvider("trusted")
    catalog.bind(weaker, lambda: trusted_provider)

    routed = HistoricalChampionRouter(registry=registry, policy=_policy(), catalog=catalog).route()

    assert routed.model == weaker
    assert routed.provider is trusted_provider
    assert routed.historical_best_percent == 80.0


def test_best_available_allowlisted_model_is_selected() -> None:
    strong = ModelIdentity("provider-a", "strong", "r1")
    medium = ModelIdentity("provider-b", "medium", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _add_score(registry, strong, 95.0, snapshot_id="strong")
    _add_score(registry, medium, 85.0, snapshot_id="medium")
    catalog = ProviderCatalog()
    catalog.bind(strong, lambda: FakeProvider("strong"))
    catalog.bind(medium, lambda: FakeProvider("medium"))

    routed = HistoricalChampionRouter(registry=registry, policy=_policy(), catalog=catalog).route()

    assert routed.model == strong
    assert routed.provider.name == "strong"
    assert routed.decision.champion.model == strong


def test_unavailable_top_model_falls_to_next_evidence_eligible_binding() -> None:
    strong = ModelIdentity("provider-a", "strong", "r1")
    medium = ModelIdentity("provider-b", "medium", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _add_score(registry, strong, 95.0, snapshot_id="strong")
    _add_score(registry, medium, 85.0, snapshot_id="medium")
    catalog = ProviderCatalog()
    catalog.bind(strong, lambda: FakeProvider("strong", is_available=False))
    catalog.bind(medium, lambda: FakeProvider("medium"))

    routed = HistoricalChampionRouter(registry=registry, policy=_policy(), catalog=catalog).route()

    assert routed.model == medium
    assert routed.historical_best_percent == 85.0


def test_explicit_candidate_filter_is_respected() -> None:
    strong = ModelIdentity("provider-a", "strong", "r1")
    medium = ModelIdentity("provider-b", "medium", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _add_score(registry, strong, 95.0, snapshot_id="strong")
    _add_score(registry, medium, 85.0, snapshot_id="medium")
    catalog = ProviderCatalog()
    catalog.bind(strong, lambda: FakeProvider("strong"))
    catalog.bind(medium, lambda: FakeProvider("medium"))

    routed = HistoricalChampionRouter(registry=registry, policy=_policy(), catalog=catalog).route(models=[medium])

    assert routed.model == medium


def test_explicit_filter_with_no_routable_candidate_fails_closed() -> None:
    strong = ModelIdentity("provider-a", "strong", "r1")
    unbound = ModelIdentity("provider-b", "unbound", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _add_score(registry, strong, 95.0, snapshot_id="strong")
    _add_score(registry, unbound, 99.0, snapshot_id="unbound")
    catalog = ProviderCatalog()
    catalog.bind(strong, lambda: FakeProvider("strong"))

    with pytest.raises(HistoricalRoutingError) as exc:
        HistoricalChampionRouter(registry=registry, policy=_policy(), catalog=catalog).route(models=[unbound])
    assert exc.value.context["reason"] == "no_routable_candidate"


def test_registered_provider_without_required_evidence_is_rejected() -> None:
    model = ModelIdentity("provider-a", "no-evidence", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: FakeProvider("provider"))
    with pytest.raises(HistoricalRoutingError) as exc:
        HistoricalChampionRouter(registry=registry, policy=_policy(), catalog=catalog).route()
    assert exc.value.context["reason"] == "no_evidence_eligible_provider"


def test_factory_exception_is_treated_as_unavailable() -> None:
    model = ModelIdentity("provider-a", "broken", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _add_score(registry, model, 90.0, snapshot_id="score")
    catalog = ProviderCatalog()

    def broken_factory():
        raise RuntimeError("boom")

    catalog.bind(model, broken_factory)
    with pytest.raises(HistoricalRoutingError) as exc:
        HistoricalChampionRouter(registry=registry, policy=_policy(), catalog=catalog).route()
    assert exc.value.context["reason"] == "no_available_provider"


def test_provider_available_exception_is_treated_as_unavailable() -> None:
    model = ModelIdentity("provider-a", "broken", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _add_score(registry, model, 90.0, snapshot_id="score")

    class BrokenAvailability(FakeProvider):
        def available(self) -> bool:
            raise RuntimeError("boom")

    catalog = ProviderCatalog()
    catalog.bind(model, lambda: BrokenAvailability("broken"))
    with pytest.raises(HistoricalRoutingError) as exc:
        HistoricalChampionRouter(registry=registry, policy=_policy(), catalog=catalog).route()
    assert exc.value.context["reason"] == "no_available_provider"


def test_build_jeeves_injects_exact_selected_provider() -> None:
    model = ModelIdentity("provider-a", "winner", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _add_score(registry, model, 93.0, snapshot_id="score")
    provider = FakeProvider("winner")
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: provider)

    selection = build_jeeves_from_historical_champion(
        registry=registry,
        policy=_policy(),
        catalog=catalog,
    )

    assert selection.routing.model == model
    assert selection.routing.provider is provider
    assert selection.core._provider is provider


def test_catalog_models_are_deterministically_sorted() -> None:
    z = ModelIdentity("z", "m", "r1")
    a = ModelIdentity("a", "m", "r1")
    catalog = ProviderCatalog()
    catalog.bind(z, lambda: FakeProvider("z"))
    catalog.bind(a, lambda: FakeProvider("a"))
    assert catalog.models() == (a, z)


def test_builtin_local_binding_is_available_without_credentials() -> None:
    model = ModelIdentity("local", "local-echo", "r1")
    binding = builtin_provider_binding(model)
    provider = binding.instantiate()
    assert provider.name == "local-echo"
    assert provider.available() is True


def test_builtin_unknown_provider_is_rejected() -> None:
    model = ModelIdentity("untrusted-plugin", "m", "r1")
    with pytest.raises(HistoricalRoutingError) as exc:
        builtin_provider_binding(model)
    assert exc.value.context["reason"] == "unsupported_builtin_provider"
