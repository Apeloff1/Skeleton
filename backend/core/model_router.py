"""Provider-neutral, evidence-bearing model routing for Jeeves.

The router treats providers as interchangeable capability endpoints rather than
hard-coded brands. Hard constraints filter candidates first; observed reliability,
quality, latency, cost, and explicit provider preference rank the survivors.

No provider call happens in this module. Routing is deterministic policy over a
registry plus immutable telemetry snapshots, which keeps it reusable for hosted
APIs, local models, image/audio backends, tests, and future engines.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Iterable, Mapping

from skeleton.intelligence.admission import ResourceBudget
from skeleton.vault.governance_registry import GovernanceContext


class RoutingError(RuntimeError):
    """Base routing failure."""


class NoRoute(RoutingError):
    """Raised when no registered endpoint satisfies hard route constraints."""


class PrivacyLevel(IntEnum):
    PUBLIC = 0
    PRIVATE = 1
    SENSITIVE = 2
    LOCAL_ONLY = 3

    @classmethod
    def parse(cls, value: "PrivacyLevel | str | int") -> "PrivacyLevel":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            key = value.strip().upper().replace("-", "_")
            try:
                return cls[key]
            except KeyError as exc:
                raise ValueError(f"unknown privacy level: {value!r}") from exc
        return cls(int(value))


def _finite_nonnegative(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and >= 0")
    return value


def _unit_interval(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be within [0, 1]")
    return value


def _names(values: Iterable[str]) -> frozenset[str]:
    return frozenset(
        text
        for raw in values
        if (text := str(raw).strip().lower())
    )


@dataclass(frozen=True)
class ModelEndpoint:
    endpoint_id: str
    provider: str
    model: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    modalities: frozenset[str] = field(default_factory=lambda: frozenset({"text"}))
    max_context_tokens: int = 0
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0
    nominal_latency_ms: float = 1000.0
    privacy_ceiling: PrivacyLevel = PrivacyLevel.PUBLIC
    local: bool = False
    enabled: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_governance_context(
        cls,
        task_type: str,
        governance: GovernanceContext,
        *,
        budget: ResourceBudget | None = None,
        context_tokens: int = 0,
        expected_output_tokens: int | None = None,
        **kwargs: Any,
    ) -> "RouteRequest":
        """Build a route request whose privacy is derived from governed records.

        Callers cannot supply or weaken privacy when governed data is present.
        When a resource budget is supplied, cost/latency/output bounds and
        governance privacy are composed into the same hard route request.
        """

        if not isinstance(governance, GovernanceContext):
            raise TypeError("governance must be a GovernanceContext")
        if "privacy" in kwargs:
            raise ValueError("governance context owns privacy")
        governed = {
            "privacy": governance.routing_privacy,
            "governance_record_ids": governance.record_ids,
            "governance_tenant_id": governance.tenant_id,
            "governance_purpose": governance.purpose,
        }
        if budget is not None:
            return cls.from_resource_budget(
                task_type,
                budget,
                context_tokens=context_tokens,
                expected_output_tokens=expected_output_tokens,
                **governed,
                **kwargs,
            )
        return cls(
            task_type=task_type,
            context_tokens=context_tokens,
            expected_output_tokens=(
                0 if expected_output_tokens is None else expected_output_tokens
            ),
            **governed,
            **kwargs,
        )

    def __post_init__(self) -> None:
        endpoint_id = self.endpoint_id.strip()
        provider = self.provider.strip()
        model = self.model.strip()
        if not endpoint_id or not provider or not model:
            raise ValueError("endpoint_id, provider and model are required")
        if isinstance(self.max_context_tokens, bool) or self.max_context_tokens < 0:
            raise ValueError("max_context_tokens must be >= 0")

        object.__setattr__(self, "endpoint_id", endpoint_id)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "capabilities", _names(self.capabilities))
        object.__setattr__(self, "modalities", _names(self.modalities))
        object.__setattr__(
            self,
            "input_cost_per_million",
            _finite_nonnegative(self.input_cost_per_million, "input_cost_per_million"),
        )
        object.__setattr__(
            self,
            "output_cost_per_million",
            _finite_nonnegative(self.output_cost_per_million, "output_cost_per_million"),
        )
        object.__setattr__(
            self,
            "nominal_latency_ms",
            _finite_nonnegative(self.nominal_latency_ms, "nominal_latency_ms"),
        )
        ceiling = PrivacyLevel.parse(self.privacy_ceiling)
        if self.local and ceiling < PrivacyLevel.LOCAL_ONLY:
            ceiling = PrivacyLevel.LOCAL_ONLY
        object.__setattr__(self, "privacy_ceiling", ceiling)
        object.__setattr__(self, "metadata", dict(self.metadata))

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            max(0, int(input_tokens)) * self.input_cost_per_million
            + max(0, int(output_tokens)) * self.output_cost_per_million
        ) / 1_000_000.0


@dataclass(frozen=True)
class RouteRequest:
    task_type: str
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    required_modalities: frozenset[str] = field(default_factory=lambda: frozenset({"text"}))
    context_tokens: int = 0
    expected_output_tokens: int = 0
    privacy: PrivacyLevel = PrivacyLevel.PUBLIC
    latency_budget_ms: float | None = None
    cost_budget: float | None = None
    preferred_providers: tuple[str, ...] = field(default_factory=tuple)
    excluded_endpoints: frozenset[str] = field(default_factory=frozenset)
    minimum_reliability: float = 0.0
    minimum_quality: float = 0.0
    governance_record_ids: tuple[str, ...] = field(default_factory=tuple)
    governance_tenant_id: str | None = None
    governance_purpose: str | None = None

    @classmethod
    def from_resource_budget(
        cls,
        task_type: str,
        budget: ResourceBudget,
        *,
        context_tokens: int = 0,
        expected_output_tokens: int | None = None,
        **kwargs: Any,
    ) -> "RouteRequest":
        """Project one admission budget into hard model-routing constraints."""

        if not isinstance(budget, ResourceBudget):
            raise TypeError("budget must be a ResourceBudget")
        output_tokens = (
            budget.max_output_tokens
            if expected_output_tokens is None
            else min(expected_output_tokens, budget.max_output_tokens)
        )
        if "latency_budget_ms" in kwargs or "cost_budget" in kwargs:
            raise ValueError(
                "resource budget owns latency_budget_ms and cost_budget"
            )
        return cls(
            task_type=task_type,
            context_tokens=context_tokens,
            expected_output_tokens=output_tokens,
            latency_budget_ms=budget.max_wall_seconds * 1000.0,
            cost_budget=budget.max_cost_usd,
            **kwargs,
        )

    def __post_init__(self) -> None:
        task_type = self.task_type.strip().lower()
        if not task_type:
            raise ValueError("task_type is required")
        if isinstance(self.context_tokens, bool) or self.context_tokens < 0:
            raise ValueError("context_tokens must be >= 0")
        if isinstance(self.expected_output_tokens, bool) or self.expected_output_tokens < 0:
            raise ValueError("expected_output_tokens must be >= 0")

        object.__setattr__(self, "task_type", task_type)
        object.__setattr__(self, "required_capabilities", _names(self.required_capabilities))
        object.__setattr__(self, "required_modalities", _names(self.required_modalities))
        object.__setattr__(self, "privacy", PrivacyLevel.parse(self.privacy))
        object.__setattr__(
            self,
            "preferred_providers",
            tuple(
                dict.fromkeys(
                    str(value).strip().lower()
                    for value in self.preferred_providers
                    if str(value).strip()
                )
            ),
        )
        object.__setattr__(self, "excluded_endpoints", _names(self.excluded_endpoints))
        if self.latency_budget_ms is not None:
            object.__setattr__(
                self,
                "latency_budget_ms",
                _finite_nonnegative(self.latency_budget_ms, "latency_budget_ms"),
            )
        if self.cost_budget is not None:
            object.__setattr__(
                self,
                "cost_budget",
                _finite_nonnegative(self.cost_budget, "cost_budget"),
            )
        object.__setattr__(
            self,
            "minimum_reliability",
            _unit_interval(self.minimum_reliability, "minimum_reliability"),
        )
        object.__setattr__(
            self,
            "minimum_quality",
            _unit_interval(self.minimum_quality, "minimum_quality"),
        )
        governed_ids = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in self.governance_record_ids
                if str(value).strip()
            )
        )
        object.__setattr__(self, "governance_record_ids", governed_ids)
        if governed_ids:
            tenant = str(self.governance_tenant_id or "").strip()
            purpose = str(self.governance_purpose or "").strip().lower()
            if not tenant:
                raise ValueError(
                    "governance_tenant_id is required for governed route requests"
                )
            if not purpose:
                raise ValueError(
                    "governance_purpose is required for governed route requests"
                )
            object.__setattr__(self, "governance_tenant_id", tenant)
            object.__setattr__(self, "governance_purpose", purpose)
        elif self.governance_tenant_id is not None or self.governance_purpose is not None:
            raise ValueError(
                "governance metadata requires governance_record_ids"
            )


@dataclass(frozen=True)
class EndpointTelemetry:
    observations: int = 0
    successes: int = 0
    reliability_ewma: float = 1.0
    quality_ewma: float = 0.5
    latency_ewma_ms: float | None = None
    cost_ewma: float | None = None
    last_observed_at: float | None = None

    @staticmethod
    def _ewma(old: float | None, value: float, alpha: float) -> float:
        return value if old is None else alpha * value + (1.0 - alpha) * old

    def updated(
        self,
        *,
        ok: bool,
        quality: float | None,
        latency_ms: float | None,
        cost: float | None,
        alpha: float,
        observed_at: float,
    ) -> "EndpointTelemetry":
        """Return a validated new sample; never partially mutate on bad input."""
        if quality is not None:
            quality = _unit_interval(quality, "quality")
        if latency_ms is not None:
            latency_ms = _finite_nonnegative(latency_ms, "latency_ms")
        if cost is not None:
            cost = _finite_nonnegative(cost, "cost")
        if not math.isfinite(observed_at) or observed_at < 0:
            raise ValueError("observed_at must be a finite non-negative timestamp")

        return EndpointTelemetry(
            observations=self.observations + 1,
            successes=self.successes + int(bool(ok)),
            reliability_ewma=self._ewma(
                self.reliability_ewma, 1.0 if ok else 0.0, alpha
            ),
            quality_ewma=(
                self.quality_ewma
                if quality is None
                else self._ewma(self.quality_ewma, quality, alpha)
            ),
            latency_ewma_ms=(
                self.latency_ewma_ms
                if latency_ms is None
                else self._ewma(self.latency_ewma_ms, latency_ms, alpha)
            ),
            cost_ewma=(
                self.cost_ewma
                if cost is None
                else self._ewma(self.cost_ewma, cost, alpha)
            ),
            last_observed_at=observed_at,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "observations": self.observations,
            "successes": self.successes,
            "reliability_ewma": round(self.reliability_ewma, 8),
            "quality_ewma": round(self.quality_ewma, 8),
            "latency_ewma_ms": (
                None
                if self.latency_ewma_ms is None
                else round(self.latency_ewma_ms, 4)
            ),
            "cost_ewma": None if self.cost_ewma is None else round(self.cost_ewma, 8),
            "last_observed_at": self.last_observed_at,
        }


@dataclass(frozen=True)
class RouteCandidate:
    endpoint_id: str
    score: float
    reliability: float
    quality: float
    estimated_latency_ms: float
    estimated_cost: float
    provider_preference: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "score": round(self.score, 8),
            "reliability": round(self.reliability, 8),
            "quality": round(self.quality, 8),
            "estimated_latency_ms": round(self.estimated_latency_ms, 4),
            "estimated_cost": round(self.estimated_cost, 8),
            "provider_preference": self.provider_preference,
        }


@dataclass(frozen=True)
class RouteDecision:
    request: RouteRequest
    selected: ModelEndpoint
    candidates: tuple[RouteCandidate, ...]
    rejected: Mapping[str, tuple[str, ...]]
    routed_at: float

    @property
    def fallback_endpoint_ids(self) -> tuple[str, ...]:
        return tuple(candidate.endpoint_id for candidate in self.candidates[1:])

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.request.task_type,
            "selected": self.selected.endpoint_id,
            "fallbacks": list(self.fallback_endpoint_ids),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "rejected": {key: list(value) for key, value in self.rejected.items()},
            "routed_at": self.routed_at,
            "governance": (
                {
                    "record_ids": list(self.request.governance_record_ids),
                    "tenant_id": self.request.governance_tenant_id,
                    "purpose": self.request.governance_purpose,
                    "privacy": self.request.privacy.name.lower(),
                }
                if self.request.governance_record_ids
                else None
            ),
        }


class ModelRouter:
    """Thread-safe registry and deterministic policy scorer."""

    def __init__(
        self,
        *,
        telemetry_alpha: float = 0.2,
        reliability_weight: float = 0.38,
        quality_weight: float = 0.38,
        latency_weight: float = 0.14,
        cost_weight: float = 0.08,
        preference_weight: float = 0.02,
    ) -> None:
        if not 0.0 < telemetry_alpha <= 1.0:
            raise ValueError("telemetry_alpha must be within (0, 1]")
        weights = (
            float(reliability_weight),
            float(quality_weight),
            float(latency_weight),
            float(cost_weight),
            float(preference_weight),
        )
        if any(not math.isfinite(value) or value < 0 for value in weights):
            raise ValueError("routing weights must be finite and non-negative")
        total = sum(weights)
        if total <= 0:
            raise ValueError("at least one routing weight must be positive")

        self.telemetry_alpha = float(telemetry_alpha)
        self.weights = tuple(value / total for value in weights)
        self._lock = threading.RLock()
        self._endpoints: dict[str, ModelEndpoint] = {}
        self._telemetry: dict[str, EndpointTelemetry] = {}

    def register(self, endpoint: ModelEndpoint, *, replace: bool = False) -> None:
        if not isinstance(endpoint, ModelEndpoint):
            raise TypeError("endpoint must be a ModelEndpoint")
        with self._lock:
            exists = endpoint.endpoint_id in self._endpoints
            if exists and not replace:
                raise ValueError(f"endpoint already registered: {endpoint.endpoint_id}")
            self._endpoints[endpoint.endpoint_id] = endpoint
            # A replacement may point at a different model/provider/configuration.
            # Never let historical measurements silently cross that identity boundary.
            if exists and replace:
                self._telemetry[endpoint.endpoint_id] = EndpointTelemetry()
            else:
                self._telemetry.setdefault(endpoint.endpoint_id, EndpointTelemetry())

    def unregister(self, endpoint_id: str) -> bool:
        endpoint_id = str(endpoint_id).strip()
        with self._lock:
            removed = self._endpoints.pop(endpoint_id, None)
            self._telemetry.pop(endpoint_id, None)
            return removed is not None

    def observe(
        self,
        endpoint_id: str,
        *,
        ok: bool,
        quality: float | None = None,
        latency_ms: float | None = None,
        cost: float | None = None,
        observed_at: float | None = None,
    ) -> None:
        endpoint_id = str(endpoint_id).strip()
        timestamp = time.time() if observed_at is None else float(observed_at)
        with self._lock:
            if endpoint_id not in self._endpoints:
                raise KeyError(f"unknown endpoint: {endpoint_id}")
            current = self._telemetry.setdefault(endpoint_id, EndpointTelemetry())
            # Assignment happens only after all validation succeeds.
            self._telemetry[endpoint_id] = current.updated(
                ok=bool(ok),
                quality=quality,
                latency_ms=latency_ms,
                cost=cost,
                alpha=self.telemetry_alpha,
                observed_at=timestamp,
            )

    @staticmethod
    def _inverse_ratio(value: float, reference: float) -> float:
        if reference <= 0:
            return 1.0 if value <= 0 else 0.0
        return max(0.0, min(1.0, 1.0 - value / reference))

    @staticmethod
    def _hard_rejections(
        endpoint: ModelEndpoint,
        telemetry: EndpointTelemetry,
        request: RouteRequest,
    ) -> list[str]:
        reasons: list[str] = []
        if not endpoint.enabled:
            reasons.append("disabled")
        if endpoint.endpoint_id.lower() in request.excluded_endpoints:
            reasons.append("excluded")

        missing_capabilities = request.required_capabilities - endpoint.capabilities
        if missing_capabilities:
            reasons.append(
                "missing capabilities: " + ",".join(sorted(missing_capabilities))
            )
        missing_modalities = request.required_modalities - endpoint.modalities
        if missing_modalities:
            reasons.append(
                "missing modalities: " + ",".join(sorted(missing_modalities))
            )

        total_context = request.context_tokens + request.expected_output_tokens
        if endpoint.max_context_tokens and total_context > endpoint.max_context_tokens:
            reasons.append(f"context {total_context} exceeds {endpoint.max_context_tokens}")
        if request.privacy > endpoint.privacy_ceiling:
            reasons.append(
                f"privacy {request.privacy.name.lower()} exceeds endpoint ceiling "
                f"{endpoint.privacy_ceiling.name.lower()}"
            )

        latency = (
            endpoint.nominal_latency_ms
            if telemetry.latency_ewma_ms is None
            else telemetry.latency_ewma_ms
        )
        if request.latency_budget_ms is not None and latency > request.latency_budget_ms:
            reasons.append(
                f"latency {latency:.2f} exceeds budget {request.latency_budget_ms:.2f}"
            )

        cost = endpoint.estimated_cost(
            request.context_tokens, request.expected_output_tokens
        )
        if telemetry.cost_ewma is not None:
            cost = max(cost, telemetry.cost_ewma)
        if request.cost_budget is not None and cost > request.cost_budget:
            reasons.append(f"cost {cost:.8f} exceeds budget {request.cost_budget:.8f}")

        if telemetry.reliability_ewma < request.minimum_reliability:
            reasons.append(
                f"reliability {telemetry.reliability_ewma:.4f} below minimum "
                f"{request.minimum_reliability:.4f}"
            )
        if telemetry.quality_ewma < request.minimum_quality:
            reasons.append(
                f"quality {telemetry.quality_ewma:.4f} below minimum "
                f"{request.minimum_quality:.4f}"
            )
        return reasons

    def route(self, request: RouteRequest) -> RouteDecision:
        if not isinstance(request, RouteRequest):
            raise TypeError("request must be a RouteRequest")

        # Endpoints and telemetry are immutable values. Copying both registries under
        # the same lock gives this route one coherent view while allowing later
        # observations/register/unregister calls to proceed independently.
        with self._lock:
            endpoints = dict(self._endpoints)
            telemetry = {
                endpoint_id: self._telemetry.get(endpoint_id, EndpointTelemetry())
                for endpoint_id in endpoints
            }

        rejected: dict[str, tuple[str, ...]] = {}
        candidates: list[RouteCandidate] = []
        reliability_weight, quality_weight, latency_weight, cost_weight, preference_weight = self.weights
        preferred = {
            provider: index
            for index, provider in enumerate(request.preferred_providers)
        }

        for endpoint_id, endpoint in endpoints.items():
            stats = telemetry[endpoint_id]
            reasons = self._hard_rejections(endpoint, stats, request)
            if reasons:
                rejected[endpoint_id] = tuple(reasons)
                continue

            latency = (
                endpoint.nominal_latency_ms
                if stats.latency_ewma_ms is None
                else stats.latency_ewma_ms
            )
            estimated_cost = endpoint.estimated_cost(
                request.context_tokens, request.expected_output_tokens
            )
            if stats.cost_ewma is not None:
                estimated_cost = max(estimated_cost, stats.cost_ewma)

            latency_reference = request.latency_budget_ms
            if latency_reference is None:
                latency_reference = max(endpoint.nominal_latency_ms * 2.0, 1.0)
            if request.cost_budget is not None:
                cost_reference = max(request.cost_budget, 1e-12)
            else:
                nominal_cost = endpoint.estimated_cost(
                    max(request.context_tokens, 1),
                    max(request.expected_output_tokens, 1),
                )
                cost_reference = max(nominal_cost * 2.0, 1e-6)

            latency_score = self._inverse_ratio(latency, latency_reference)
            cost_score = self._inverse_ratio(estimated_cost, cost_reference)
            provider_key = endpoint.provider.lower()
            preference_index = preferred.get(provider_key)
            if preference_index is None:
                preference_score = 0.0
                preference_rank = len(preferred) + 1
            else:
                preference_score = 1.0 / (preference_index + 1)
                preference_rank = preference_index

            score = (
                stats.reliability_ewma * reliability_weight
                + stats.quality_ewma * quality_weight
                + latency_score * latency_weight
                + cost_score * cost_weight
                + preference_score * preference_weight
            )
            candidates.append(
                RouteCandidate(
                    endpoint_id=endpoint_id,
                    score=score,
                    reliability=stats.reliability_ewma,
                    quality=stats.quality_ewma,
                    estimated_latency_ms=latency,
                    estimated_cost=estimated_cost,
                    provider_preference=preference_rank,
                )
            )

        candidates.sort(
            key=lambda candidate: (
                -candidate.score,
                candidate.provider_preference,
                candidate.estimated_latency_ms,
                candidate.estimated_cost,
                candidate.endpoint_id,
            )
        )
        if not candidates:
            detail = "; ".join(
                f"{endpoint_id}: {', '.join(reasons)}"
                for endpoint_id, reasons in sorted(rejected.items())
            )
            raise NoRoute(f"no endpoint satisfies route request ({detail})")

        return RouteDecision(
            request=request,
            selected=endpoints[candidates[0].endpoint_id],
            candidates=tuple(candidates),
            rejected=rejected,
            routed_at=time.time(),
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            endpoints = sorted(self._endpoints.values(), key=lambda row: row.endpoint_id)
            telemetry = dict(self._telemetry)

        return {
            "endpoints": [
                {
                    "endpoint_id": endpoint.endpoint_id,
                    "provider": endpoint.provider,
                    "model": endpoint.model,
                    "capabilities": sorted(endpoint.capabilities),
                    "modalities": sorted(endpoint.modalities),
                    "max_context_tokens": endpoint.max_context_tokens,
                    "privacy_ceiling": endpoint.privacy_ceiling.name.lower(),
                    "local": endpoint.local,
                    "enabled": endpoint.enabled,
                    "telemetry": telemetry.get(
                        endpoint.endpoint_id, EndpointTelemetry()
                    ).snapshot(),
                }
                for endpoint in endpoints
            ]
        }
