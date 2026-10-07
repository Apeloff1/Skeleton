"""Trusted runtime routing for the Jeeves historical-model selector.

Historical benchmark evidence is data, not executable configuration.  This
module keeps that boundary explicit: a benchmark winner can only become a live
Jeeves provider when an operator has registered the exact :class:`ModelIdentity`
in a trusted :class:`ProviderCatalog`.

The catalog therefore acts as the capability boundary between offline evidence
and runtime model invocation. Unknown historical winners, unavailable providers,
and malformed provider implementations fail closed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from skeleton.jeeves.historical_models import (
    ChampionDecision,
    HistoricalModelError,
    HistoricalModelRegistry,
    ModelIdentity,
    ModelScore,
    SelectionPolicy,
)


class HistoricalRoutingError(HistoricalModelError):
    """Runtime routing failure after historical scoring."""

    code = "JVS.HISTORICAL_ROUTING"
    http_status = 503


ProviderFactory = Callable[[], Any]


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    """Explicit allowlisted mapping from a model identity to a provider factory."""

    model: ModelIdentity
    factory: ProviderFactory
    label: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.model, ModelIdentity):
            raise HistoricalRoutingError(
                "binding model must be ModelIdentity",
                context={"reason": "invalid_model"},
            )
        if not callable(self.factory):
            raise HistoricalRoutingError(
                "provider factory must be callable",
                context={"reason": "invalid_factory", "model": self.model.key},
            )
        if self.label and (not isinstance(self.label, str) or len(self.label) > 160):
            raise HistoricalRoutingError(
                "binding label must be a bounded string",
                context={"reason": "invalid_label", "model": self.model.key},
            )

    def instantiate(self) -> Any:
        try:
            provider = self.factory()
        except Exception as exc:
            raise HistoricalRoutingError(
                "provider factory failed",
                context={"reason": "factory_failed", "model": self.model.key},
                cause=exc,
            ) from exc
        _validate_provider(provider, model=self.model)
        return provider


@dataclass(slots=True)
class ProviderCatalog:
    """Trusted, duplicate-resistant provider allowlist."""

    _bindings: dict[ModelIdentity, ProviderBinding] = field(default_factory=dict, init=False)

    def register(self, binding: ProviderBinding) -> None:
        if not isinstance(binding, ProviderBinding):
            raise HistoricalRoutingError(
                "binding must be ProviderBinding",
                context={"reason": "invalid_binding"},
            )
        if binding.model in self._bindings:
            raise HistoricalRoutingError(
                "model identity is already bound",
                context={"reason": "duplicate_binding", "model": binding.model.key},
            )
        self._bindings[binding.model] = binding

    def bind(self, model: ModelIdentity, factory: ProviderFactory, *, label: str = "") -> ProviderBinding:
        binding = ProviderBinding(model=model, factory=factory, label=label)
        self.register(binding)
        return binding

    def contains(self, model: ModelIdentity) -> bool:
        return model in self._bindings

    def binding(self, model: ModelIdentity) -> ProviderBinding:
        try:
            return self._bindings[model]
        except KeyError as exc:
            raise HistoricalRoutingError(
                "historical model is not allowlisted for runtime use",
                context={"reason": "unbound_model", "model": model.key},
            ) from exc

    def models(self) -> tuple[ModelIdentity, ...]:
        return tuple(sorted(self._bindings))

    def probe_available(self) -> tuple[tuple[ModelIdentity, Any], ...]:
        """Instantiate and retain providers that explicitly report availability.

        Factories are evaluated once per routing decision. A provider that is
        missing its credentials or otherwise unavailable is omitted from the
        candidate set rather than causing the selector to silently substitute an
        unregistered backend.
        """
        available: list[tuple[ModelIdentity, Any]] = []
        for model in self.models():
            try:
                provider = self.binding(model).instantiate()
            except HistoricalRoutingError:
                continue
            try:
                is_available = provider.available()
            except Exception:
                continue
            if is_available is True:
                available.append((model, provider))
        return tuple(available)


@dataclass(frozen=True, slots=True)
class RoutedChampion:
    """Historical selection paired with the exact trusted runtime provider."""

    decision: ChampionDecision
    selected: ModelScore
    provider: Any

    @property
    def model(self) -> ModelIdentity:
        return self.selected.model

    @property
    def historical_best_percent(self) -> float:
        return self.selected.percent


@dataclass(frozen=True, slots=True)
class HistoricalJeevesSelection:
    """Constructed Jeeves core plus the evidence-backed routing decision."""

    core: Any
    routing: RoutedChampion


@dataclass(slots=True)
class HistoricalChampionRouter:
    """Select the strongest *available and allowlisted* historical model."""

    registry: HistoricalModelRegistry
    policy: SelectionPolicy
    catalog: ProviderCatalog

    def __post_init__(self) -> None:
        if not isinstance(self.registry, HistoricalModelRegistry):
            raise HistoricalRoutingError(
                "registry must be HistoricalModelRegistry",
                context={"reason": "invalid_registry"},
            )
        if not isinstance(self.policy, SelectionPolicy):
            raise HistoricalRoutingError(
                "policy must be SelectionPolicy",
                context={"reason": "invalid_policy"},
            )
        if not isinstance(self.catalog, ProviderCatalog):
            raise HistoricalRoutingError(
                "catalog must be ProviderCatalog",
                context={"reason": "invalid_catalog"},
            )

    def route(self, *, models: Iterable[ModelIdentity] | None = None) -> RoutedChampion:
        probed = self.catalog.probe_available()
        if not probed:
            raise HistoricalRoutingError(
                "no allowlisted historical providers are available",
                context={"reason": "no_available_provider"},
            )
        providers = {model: provider for model, provider in probed}
        candidates = set(providers)
        if models is not None:
            requested = set(models)
            if any(not isinstance(model, ModelIdentity) for model in requested):
                raise HistoricalRoutingError(
                    "models must contain ModelIdentity values",
                    context={"reason": "invalid_model"},
                )
            candidates.intersection_update(requested)
        if not candidates:
            raise HistoricalRoutingError(
                "no requested model is both allowlisted and available",
                context={"reason": "no_routable_candidate"},
            )
        try:
            decision = self.registry.select_champion(self.policy, models=sorted(candidates))
        except HistoricalModelError as exc:
            raise HistoricalRoutingError(
                "no routable model satisfied the historical evidence policy",
                context={"reason": "no_evidence_eligible_provider", "detail": exc.context},
                cause=exc,
            ) from exc
        selected = decision.champion
        provider = providers[selected.model]
        return RoutedChampion(decision=decision, selected=selected, provider=provider)


def _validate_provider(provider: Any, *, model: ModelIdentity) -> None:
    if provider is None:
        raise HistoricalRoutingError(
            "provider factory returned None",
            context={"reason": "invalid_provider", "model": model.key},
        )
    complete = getattr(provider, "complete", None)
    available = getattr(provider, "available", None)
    if not callable(complete) or not callable(available):
        raise HistoricalRoutingError(
            "provider does not satisfy the Jeeves provider contract",
            context={"reason": "invalid_provider", "model": model.key},
        )
    name = getattr(provider, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise HistoricalRoutingError(
            "provider must expose a non-empty name",
            context={"reason": "invalid_provider", "model": model.key},
        )
    supports_system = getattr(provider, "supports_system_prompt", None)
    if not isinstance(supports_system, bool):
        raise HistoricalRoutingError(
            "provider must declare supports_system_prompt",
            context={"reason": "invalid_provider", "model": model.key},
        )


def builtin_provider_binding(
    model: ModelIdentity,
    *,
    retriever: Any = None,
) -> ProviderBinding:
    """Create a trusted binding for Skeleton's built-in provider families.

    The provider family comes from the allowlisted ``ModelIdentity.provider``;
    benchmark data cannot import modules, name classes, or inject arbitrary
    constructor arguments.
    """
    from skeleton.jeeves.providers import AnthropicProvider, LocalEchoProvider, OpenAIProvider

    if model.provider == "openai":
        return ProviderBinding(
            model=model,
            factory=lambda: OpenAIProvider(model=model.model),
            label="built-in OpenAI provider",
        )
    if model.provider == "anthropic":
        return ProviderBinding(
            model=model,
            factory=lambda: AnthropicProvider(model=model.model),
            label="built-in Anthropic provider",
        )
    if model.provider in {"local", "local-echo"}:
        return ProviderBinding(
            model=model,
            factory=lambda: LocalEchoProvider(retriever=retriever),
            label="built-in local echo provider",
        )
    raise HistoricalRoutingError(
        "model provider has no built-in binding",
        context={"reason": "unsupported_builtin_provider", "model": model.key},
    )


def build_jeeves_from_historical_champion(
    *,
    registry: HistoricalModelRegistry,
    policy: SelectionPolicy,
    catalog: ProviderCatalog,
    bus: Any = None,
    retriever: Any = None,
    cycle: Any = None,
    models: Iterable[ModelIdentity] | None = None,
) -> HistoricalJeevesSelection:
    """Build ``JeevesCore`` with the strongest trusted historical candidate."""
    from skeleton.jeeves.llm_core import JeevesCore

    routing = HistoricalChampionRouter(
        registry=registry,
        policy=policy,
        catalog=catalog,
    ).route(models=models)
    core = JeevesCore(
        bus=bus,
        retriever=retriever,
        provider=routing.provider,
        cycle=cycle,
    )
    return HistoricalJeevesSelection(core=core, routing=routing)