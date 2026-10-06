"""Deterministic model placement and failover authority for AI chat.

This module is deliberately a *decision plane*.  It never instantiates provider
SDKs, reads credentials, or dispatches inference.  It binds one turn's immutable
requirements and remaining budget to a health-qualified endpoint set, producing
an evidence-bearing placement receipt that the canonical provider runtime can
consume.

October 2026 invariants implemented here:

* fallback cannot weaken privacy, locality, jurisdiction, modality, context,
  quality, reliability, deadline, or cost requirements;
* stale/unknown health fails closed;
* open circuit breakers and saturated endpoints are not selectable;
* degraded endpoints are policy-controlled and rank behind healthy endpoints;
* placement is deterministic for identical evidence;
* provider failover is only authorized for explicitly retryable failure classes;
* a fallback must have been admitted by the original placement receipt;
* every decision is non-executing and digest-bound to request, policy, budget,
  endpoint profiles, and endpoint health observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence


PLACEMENT_SCHEMA_VERSION = 1
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#@-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PlacementError(ValueError):
    """Placement evidence is malformed or violates a fail-closed invariant."""


class PrivacyTier(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    SENSITIVE = 2
    RESTRICTED = 3


class EndpointState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OPEN = "open"


class ProviderFailureKind(str, Enum):
    TRANSIENT = "transient"
    CAPACITY = "capacity"
    UNAVAILABLE = "unavailable"
    POLICY = "policy"
    PROTOCOL = "protocol"
    QUALITY = "quality"
    UNKNOWN = "unknown"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PlacementError("value is not canonical-json encodable") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise PlacementError(f"{field} must be a canonical token")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise PlacementError(f"{field} must be lowercase sha256")
    return value


def _finite(value: object, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlacementError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PlacementError(f"{field} must be finite numeric")
    if minimum is not None and result < minimum:
        raise PlacementError(f"{field} must be >= {minimum}")
    return result


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PlacementError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PlacementError(f"{field} must be a non-negative integer")
    return value


def _bounded_unit(value: object, field: str) -> float:
    result = _finite(value, field, minimum=0.0)
    if result > 1.0:
        raise PlacementError(f"{field} must be <= 1.0")
    return result


def _tokens(values: Iterable[str], field: str) -> tuple[str, ...]:
    result = tuple(sorted({_token(value, field) for value in values}))
    if not result:
        raise PlacementError(f"{field} must not be empty")
    return result


@dataclass(frozen=True, slots=True)
class EndpointProfile:
    endpoint_id: str
    provider_id: str
    model_id: str
    modalities: tuple[str, ...]
    privacy_ceiling: PrivacyTier | int
    local: bool
    jurisdictions: tuple[str, ...]
    context_tokens: int
    max_output_tokens: int
    quality: float
    reliability: float
    p95_latency_ms: int
    cost_per_1k_tokens_usd: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint_id", _token(self.endpoint_id, "endpoint_id"))
        object.__setattr__(self, "provider_id", _token(self.provider_id, "provider_id"))
        object.__setattr__(self, "model_id", _token(self.model_id, "model_id"))
        object.__setattr__(self, "modalities", _tokens(self.modalities, "modalities"))
        try:
            object.__setattr__(self, "privacy_ceiling", PrivacyTier(self.privacy_ceiling))
        except ValueError as exc:
            raise PlacementError("invalid privacy_ceiling") from exc
        if not isinstance(self.local, bool):
            raise PlacementError("local must be boolean")
        normalized_jurisdictions = tuple(
            sorted({_token(item, "jurisdictions") for item in self.jurisdictions})
        )
        object.__setattr__(self, "jurisdictions", normalized_jurisdictions)
        object.__setattr__(
            self, "context_tokens", _positive_int(self.context_tokens, "context_tokens")
        )
        object.__setattr__(
            self,
            "max_output_tokens",
            _positive_int(self.max_output_tokens, "max_output_tokens"),
        )
        object.__setattr__(self, "quality", _bounded_unit(self.quality, "quality"))
        object.__setattr__(
            self, "reliability", _bounded_unit(self.reliability, "reliability")
        )
        object.__setattr__(
            self,
            "p95_latency_ms",
            _positive_int(self.p95_latency_ms, "p95_latency_ms"),
        )
        object.__setattr__(
            self,
            "cost_per_1k_tokens_usd",
            _finite(
                self.cost_per_1k_tokens_usd,
                "cost_per_1k_tokens_usd",
                minimum=0.0,
            ),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "modalities": list(self.modalities),
            "privacy_ceiling": self.privacy_ceiling.name.lower(),
            "local": self.local,
            "jurisdictions": list(self.jurisdictions),
            "context_tokens": self.context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "quality": self.quality,
            "reliability": self.reliability,
            "p95_latency_ms": self.p95_latency_ms,
            "cost_per_1k_tokens_usd": self.cost_per_1k_tokens_usd,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class EndpointHealth:
    endpoint_id: str
    state: EndpointState | str
    observed_at: float
    max_age_s: float
    in_flight: int
    max_concurrency: int
    consecutive_failures: int = 0
    breaker_until: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint_id", _token(self.endpoint_id, "endpoint_id"))
        try:
            object.__setattr__(self, "state", EndpointState(self.state))
        except ValueError as exc:
            raise PlacementError("invalid endpoint health state") from exc
        object.__setattr__(
            self, "observed_at", _finite(self.observed_at, "observed_at", minimum=0.0)
        )
        object.__setattr__(self, "max_age_s", _finite(self.max_age_s, "max_age_s", minimum=0.001))
        object.__setattr__(self, "in_flight", _nonnegative_int(self.in_flight, "in_flight"))
        object.__setattr__(
            self,
            "max_concurrency",
            _positive_int(self.max_concurrency, "max_concurrency"),
        )
        object.__setattr__(
            self,
            "consecutive_failures",
            _nonnegative_int(self.consecutive_failures, "consecutive_failures"),
        )
        object.__setattr__(
            self,
            "breaker_until",
            _finite(self.breaker_until, "breaker_until", minimum=0.0),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "state": self.state.value,
            "observed_at": self.observed_at,
            "max_age_s": self.max_age_s,
            "in_flight": self.in_flight,
            "max_concurrency": self.max_concurrency,
            "consecutive_failures": self.consecutive_failures,
            "breaker_until": self.breaker_until,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class PlacementBudget:
    model_calls_remaining: int
    wall_time_ms_remaining: int
    cost_usd_remaining: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_calls_remaining",
            _nonnegative_int(self.model_calls_remaining, "model_calls_remaining"),
        )
        object.__setattr__(
            self,
            "wall_time_ms_remaining",
            _nonnegative_int(self.wall_time_ms_remaining, "wall_time_ms_remaining"),
        )
        object.__setattr__(
            self,
            "cost_usd_remaining",
            _finite(self.cost_usd_remaining, "cost_usd_remaining", minimum=0.0),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "model_calls_remaining": self.model_calls_remaining,
            "wall_time_ms_remaining": self.wall_time_ms_remaining,
            "cost_usd_remaining": self.cost_usd_remaining,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class PlacementRequest:
    operation_id: str
    request_digest: str
    required_modalities: tuple[str, ...]
    privacy_tier: PrivacyTier | int
    local_only: bool
    allowed_jurisdictions: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    minimum_quality: float
    minimum_reliability: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _token(self.operation_id, "operation_id"))
        object.__setattr__(self, "request_digest", _sha(self.request_digest, "request_digest"))
        object.__setattr__(
            self,
            "required_modalities",
            _tokens(self.required_modalities, "required_modalities"),
        )
        try:
            object.__setattr__(self, "privacy_tier", PrivacyTier(self.privacy_tier))
        except ValueError as exc:
            raise PlacementError("invalid privacy_tier") from exc
        if not isinstance(self.local_only, bool):
            raise PlacementError("local_only must be boolean")
        object.__setattr__(
            self,
            "allowed_jurisdictions",
            tuple(
                sorted(
                    {
                        _token(item, "allowed_jurisdictions")
                        for item in self.allowed_jurisdictions
                    }
                )
            ),
        )
        object.__setattr__(self, "input_tokens", _positive_int(self.input_tokens, "input_tokens"))
        object.__setattr__(
            self, "output_tokens", _positive_int(self.output_tokens, "output_tokens")
        )
        object.__setattr__(
            self, "minimum_quality", _bounded_unit(self.minimum_quality, "minimum_quality")
        )
        object.__setattr__(
            self,
            "minimum_reliability",
            _bounded_unit(self.minimum_reliability, "minimum_reliability"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "request_digest": self.request_digest,
            "required_modalities": list(self.required_modalities),
            "privacy_tier": self.privacy_tier.name.lower(),
            "local_only": self.local_only,
            "allowed_jurisdictions": list(self.allowed_jurisdictions),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "minimum_quality": self.minimum_quality,
            "minimum_reliability": self.minimum_reliability,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class PlacementPolicy:
    policy_id: str
    allow_degraded: bool = False
    max_call_cost_usd: float = 100.0
    schema_version: int = PLACEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _token(self.policy_id, "policy_id"))
        if not isinstance(self.allow_degraded, bool):
            raise PlacementError("allow_degraded must be boolean")
        object.__setattr__(
            self,
            "max_call_cost_usd",
            _finite(self.max_call_cost_usd, "max_call_cost_usd", minimum=0.0),
        )
        if self.schema_version != PLACEMENT_SCHEMA_VERSION:
            raise PlacementError("unsupported placement policy schema")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "allow_degraded": self.allow_degraded,
            "max_call_cost_usd": self.max_call_cost_usd,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class EndpointAdmission:
    endpoint_id: str
    admitted: bool
    reasons: tuple[str, ...]
    estimated_cost_usd: float
    profile_digest: str
    health_digest: str

    def payload(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "admitted": self.admitted,
            "reasons": list(self.reasons),
            "estimated_cost_usd": self.estimated_cost_usd,
            "profile_digest": self.profile_digest,
            "health_digest": self.health_digest,
        }


@dataclass(frozen=True, slots=True)
class PlacementDecision:
    request_digest: str
    placement_request_digest: str
    policy_digest: str
    budget_digest: str
    budget: PlacementBudget
    selected_endpoint_id: str | None
    fallback_endpoint_ids: tuple[str, ...]
    admissions: tuple[EndpointAdmission, ...]
    observed_at: float
    authority_scope: str = "model-placement-only"
    production_authority: bool = False
    schema_version: int = PLACEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in (
            "request_digest",
            "placement_request_digest",
            "policy_digest",
            "budget_digest",
        ):
            object.__setattr__(self, field, _sha(getattr(self, field), field))
        if not isinstance(self.budget, PlacementBudget):
            raise PlacementError("budget must be PlacementBudget")
        if self.budget_digest != self.budget.digest:
            raise PlacementError("budget digest does not match budget snapshot")
        if self.selected_endpoint_id is not None:
            object.__setattr__(
                self,
                "selected_endpoint_id",
                _token(self.selected_endpoint_id, "selected_endpoint_id"),
            )
        object.__setattr__(
            self,
            "fallback_endpoint_ids",
            tuple(_token(item, "fallback_endpoint_ids") for item in self.fallback_endpoint_ids),
        )
        object.__setattr__(
            self, "observed_at", _finite(self.observed_at, "observed_at", minimum=0.0)
        )
        if self.authority_scope != "model-placement-only":
            raise PlacementError("placement authority scope escalation")
        if self.production_authority is not False:
            raise PlacementError("placement decision cannot execute inference")
        if self.schema_version != PLACEMENT_SCHEMA_VERSION:
            raise PlacementError("unsupported placement decision schema")
        admitted = {item.endpoint_id for item in self.admissions if item.admitted}
        if self.selected_endpoint_id is None:
            if self.fallback_endpoint_ids:
                raise PlacementError("fallbacks require a selected endpoint")
        else:
            if self.selected_endpoint_id not in admitted:
                raise PlacementError("selected endpoint was not admitted")
            if any(item not in admitted for item in self.fallback_endpoint_ids):
                raise PlacementError("fallback endpoint was not admitted")
            if self.selected_endpoint_id in self.fallback_endpoint_ids:
                raise PlacementError("selected endpoint cannot also be fallback")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_digest": self.request_digest,
            "placement_request_digest": self.placement_request_digest,
            "policy_digest": self.policy_digest,
            "budget_digest": self.budget_digest,
            "budget": self.budget.payload(),
            "selected_endpoint_id": self.selected_endpoint_id,
            "fallback_endpoint_ids": list(self.fallback_endpoint_ids),
            "admissions": [item.payload() for item in self.admissions],
            "observed_at": self.observed_at,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def decision_digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class FailoverDecision:
    authorized: bool
    endpoint_id: str | None
    reasons: tuple[str, ...]
    prior_placement_digest: str
    fresh_placement_digest: str
    failure_kind: ProviderFailureKind | str
    authority_scope: str = "provider-failover-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.authorized, bool):
            raise PlacementError("authorized must be boolean")
        if self.endpoint_id is not None:
            object.__setattr__(self, "endpoint_id", _token(self.endpoint_id, "endpoint_id"))
        object.__setattr__(
            self,
            "prior_placement_digest",
            _sha(self.prior_placement_digest, "prior_placement_digest"),
        )
        object.__setattr__(
            self,
            "fresh_placement_digest",
            _sha(self.fresh_placement_digest, "fresh_placement_digest"),
        )
        try:
            object.__setattr__(self, "failure_kind", ProviderFailureKind(self.failure_kind))
        except ValueError as exc:
            raise PlacementError("invalid provider failure kind") from exc
        if self.authority_scope != "provider-failover-only":
            raise PlacementError("failover authority scope escalation")
        if self.production_authority is not False:
            raise PlacementError("failover decision cannot dispatch inference")
        if self.authorized and (self.endpoint_id is None or self.reasons):
            raise PlacementError("authorized failover must have endpoint and no reasons")
        if not self.authorized and not self.reasons:
            raise PlacementError("denied failover must explain why")

    def payload(self) -> dict[str, Any]:
        return {
            "authorized": self.authorized,
            "endpoint_id": self.endpoint_id,
            "reasons": list(self.reasons),
            "prior_placement_digest": self.prior_placement_digest,
            "fresh_placement_digest": self.fresh_placement_digest,
            "failure_kind": self.failure_kind.value,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def decision_digest(self) -> str:
        return _digest(self.payload())


class ModelPlacementEngine:
    """Deterministic, non-executing endpoint selection authority."""

    def __init__(self, policy: PlacementPolicy) -> None:
        if not isinstance(policy, PlacementPolicy):
            raise TypeError("policy must be PlacementPolicy")
        self.policy = policy

    @staticmethod
    def _estimate_cost(profile: EndpointProfile, request: PlacementRequest) -> float:
        return (
            (request.input_tokens + request.output_tokens)
            / 1000.0
            * profile.cost_per_1k_tokens_usd
        )

    def _admit(
        self,
        *,
        profile: EndpointProfile,
        health: EndpointHealth | None,
        request: PlacementRequest,
        budget: PlacementBudget,
        observed_at: float,
    ) -> EndpointAdmission:
        reasons: list[str] = []
        estimated_cost = self._estimate_cost(profile, request)
        if health is None:
            return EndpointAdmission(
                endpoint_id=profile.endpoint_id,
                admitted=False,
                reasons=("health-missing",),
                estimated_cost_usd=estimated_cost,
                profile_digest=profile.digest,
                health_digest="0" * 64,
            )
        if health.endpoint_id != profile.endpoint_id:
            reasons.append("health-endpoint-mismatch")
        if observed_at < health.observed_at:
            reasons.append("health-observation-from-future")
        elif observed_at - health.observed_at > health.max_age_s:
            reasons.append("health-stale")
        if health.state is EndpointState.OPEN:
            reasons.append("endpoint-open")
        elif health.state is EndpointState.DEGRADED and not self.policy.allow_degraded:
            reasons.append("endpoint-degraded-not-admitted")
        if health.breaker_until > observed_at:
            reasons.append("circuit-breaker-open")
        if health.in_flight >= health.max_concurrency:
            reasons.append("endpoint-saturated")
        if request.local_only and not profile.local:
            reasons.append("local-only-requirement")
        if request.privacy_tier > profile.privacy_ceiling:
            reasons.append("privacy-ceiling-insufficient")
        if request.allowed_jurisdictions and not (
            set(request.allowed_jurisdictions) & set(profile.jurisdictions)
        ):
            reasons.append("jurisdiction-not-admitted")
        if not set(request.required_modalities).issubset(profile.modalities):
            reasons.append("required-modality-missing")
        if request.input_tokens + request.output_tokens > profile.context_tokens:
            reasons.append("context-capacity-insufficient")
        if request.output_tokens > profile.max_output_tokens:
            reasons.append("output-capacity-insufficient")
        if profile.quality < request.minimum_quality:
            reasons.append("quality-floor-not-met")
        if profile.reliability < request.minimum_reliability:
            reasons.append("reliability-floor-not-met")
        if profile.p95_latency_ms > budget.wall_time_ms_remaining:
            reasons.append("deadline-budget-insufficient")
        if budget.model_calls_remaining < 1:
            reasons.append("model-call-budget-exhausted")
        if estimated_cost > budget.cost_usd_remaining:
            reasons.append("turn-cost-budget-insufficient")
        if estimated_cost > self.policy.max_call_cost_usd:
            reasons.append("call-cost-policy-exceeded")
        return EndpointAdmission(
            endpoint_id=profile.endpoint_id,
            admitted=not reasons,
            reasons=tuple(sorted(set(reasons))),
            estimated_cost_usd=estimated_cost,
            profile_digest=profile.digest,
            health_digest=health.digest,
        )

    @staticmethod
    def _rank(
        profile: EndpointProfile,
        health: EndpointHealth,
        admission: EndpointAdmission,
    ) -> tuple[object, ...]:
        health_rank = 0 if health.state is EndpointState.HEALTHY else 1
        return (
            health_rank,
            -profile.quality,
            -profile.reliability,
            profile.p95_latency_ms,
            admission.estimated_cost_usd,
            health.in_flight / health.max_concurrency,
            profile.endpoint_id,
        )

    def plan(
        self,
        *,
        request: PlacementRequest,
        budget: PlacementBudget,
        endpoints: Sequence[EndpointProfile],
        health: Mapping[str, EndpointHealth],
        observed_at: float,
        excluded_endpoint_ids: Iterable[str] = (),
    ) -> PlacementDecision:
        if not isinstance(request, PlacementRequest):
            raise TypeError("request must be PlacementRequest")
        if not isinstance(budget, PlacementBudget):
            raise TypeError("budget must be PlacementBudget")
        now = _finite(observed_at, "observed_at", minimum=0.0)
        excluded = {_token(item, "excluded_endpoint_ids") for item in excluded_endpoint_ids}
        profiles: dict[str, EndpointProfile] = {}
        for profile in endpoints:
            if not isinstance(profile, EndpointProfile):
                raise TypeError("endpoints must contain EndpointProfile")
            if profile.endpoint_id in profiles:
                raise PlacementError("duplicate endpoint_id")
            profiles[profile.endpoint_id] = profile

        admissions: list[EndpointAdmission] = []
        eligible: list[tuple[tuple[object, ...], EndpointProfile]] = []
        for endpoint_id in sorted(profiles):
            profile = profiles[endpoint_id]
            item = self._admit(
                profile=profile,
                health=health.get(endpoint_id),
                request=request,
                budget=budget,
                observed_at=now,
            )
            if endpoint_id in excluded:
                item = EndpointAdmission(
                    endpoint_id=item.endpoint_id,
                    admitted=False,
                    reasons=tuple(sorted(set(item.reasons + ("endpoint-excluded",)))),
                    estimated_cost_usd=item.estimated_cost_usd,
                    profile_digest=item.profile_digest,
                    health_digest=item.health_digest,
                )
            admissions.append(item)
            if item.admitted:
                endpoint_health = health[endpoint_id]
                eligible.append((self._rank(profile, endpoint_health, item), profile))

        eligible.sort(key=lambda item: item[0])
        ordered_ids = tuple(profile.endpoint_id for _, profile in eligible)
        selected = ordered_ids[0] if ordered_ids else None
        return PlacementDecision(
            request_digest=request.request_digest,
            placement_request_digest=request.digest,
            policy_digest=self.policy.digest,
            budget_digest=budget.digest,
            budget=budget,
            selected_endpoint_id=selected,
            fallback_endpoint_ids=ordered_ids[1:],
            admissions=tuple(admissions),
            observed_at=now,
        )

    def authorize_failover(
        self,
        *,
        prior: PlacementDecision,
        failure_kind: ProviderFailureKind | str,
        fresh: PlacementDecision,
    ) -> FailoverDecision:
        if not isinstance(prior, PlacementDecision) or not isinstance(fresh, PlacementDecision):
            raise TypeError("prior and fresh must be PlacementDecision")
        try:
            failure = ProviderFailureKind(failure_kind)
        except ValueError as exc:
            raise PlacementError("invalid provider failure kind") from exc
        reasons: list[str] = []
        if prior.policy_digest != self.policy.digest or fresh.policy_digest != self.policy.digest:
            reasons.append("placement-policy-mismatch")
        if prior.request_digest != fresh.request_digest:
            reasons.append("request-digest-mismatch")
        if prior.placement_request_digest != fresh.placement_request_digest:
            reasons.append("placement-requirements-changed")
        if (
            fresh.budget.model_calls_remaining > prior.budget.model_calls_remaining
            or fresh.budget.wall_time_ms_remaining > prior.budget.wall_time_ms_remaining
            or fresh.budget.cost_usd_remaining > prior.budget.cost_usd_remaining
        ):
            reasons.append("failover-budget-amplified")
        if prior.selected_endpoint_id is None:
            reasons.append("no-prior-selected-endpoint")
        if failure not in {
            ProviderFailureKind.TRANSIENT,
            ProviderFailureKind.CAPACITY,
            ProviderFailureKind.UNAVAILABLE,
        }:
            reasons.append("failure-class-not-failover-eligible")
        candidate = fresh.selected_endpoint_id
        if candidate is None:
            reasons.append("no-fresh-fallback")
        elif candidate == prior.selected_endpoint_id:
            reasons.append("fresh-plan-reselected-failed-endpoint")
        elif candidate not in prior.fallback_endpoint_ids:
            reasons.append("fallback-not-admitted-by-prior-receipt")
        normalized = tuple(sorted(set(reasons)))
        return FailoverDecision(
            authorized=not normalized,
            endpoint_id=candidate if not normalized else None,
            reasons=normalized,
            prior_placement_digest=prior.decision_digest,
            fresh_placement_digest=fresh.decision_digest,
            failure_kind=failure,
        )


__all__ = [
    "PLACEMENT_SCHEMA_VERSION",
    "EndpointAdmission",
    "EndpointHealth",
    "EndpointProfile",
    "EndpointState",
    "FailoverDecision",
    "ModelPlacementEngine",
    "PlacementBudget",
    "PlacementDecision",
    "PlacementError",
    "PlacementPolicy",
    "PlacementRequest",
    "PrivacyTier",
    "ProviderFailureKind",
]
