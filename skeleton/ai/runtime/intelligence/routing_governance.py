"""Evidence-bound qualification layer for the canonical router registry.

October-2026 control-plane invariants:
* exact registry snapshot fencing;
* fresh independently verified health/risk evidence;
* deterministic capability/capacity/cost qualification;
* fail-closed handling of missing or stale evidence;
* descriptive routing decisions never grant model-execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef, canonical_json_bytes
from skeleton.frontier.runtime.model_routing import ProviderMetadataError
from skeleton.intelligence.router_registry import RouterRegistry


ROUTING_GOVERNANCE_VERSION = 1
ROUTING_AUTHORITY_SCOPE = "routing-catalog-only"
_MAX_EVIDENCE = 128


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderMetadataError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ProviderMetadataError(f"{field} must be finite and non-negative")
    return result


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ProviderMetadataError(f"{field} must be normalized non-empty text")
    return value


def _tokens(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ProviderMetadataError(f"{field} must be an iterable")
    result = tuple(sorted({_token(item, field) for item in values}))
    if not result:
        raise ProviderMetadataError(f"{field} must not be empty")
    return result


def _sha(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ProviderMetadataError(f"{field} must be lowercase sha256")
    return value


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise ProviderMetadataError("evidence must contain EvidenceRef")
    indexed: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise ProviderMetadataError("evidence must contain EvidenceRef")
        _sha(item.digest, "evidence.digest")
        indexed[(item.source, item.digest, item.category)] = item
    if not indexed or len(indexed) > _MAX_EVIDENCE:
        raise ProviderMetadataError("evidence must contain 1..128 unique refs")
    return tuple(indexed[key] for key in sorted(indexed))


def _digest(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class RouteObservation:
    provider_id: str
    model: str
    health_score: float
    risk_score: float
    observed_at: float
    expires_at: float
    evidence: tuple[EvidenceRef, ...]
    verifier_id: str
    verifier_digest: str
    independent: bool = True
    authority_scope: str = ROUTING_AUTHORITY_SCOPE

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _token(self.provider_id, "provider_id"))
        object.__setattr__(self, "model", _token(self.model, "model"))
        health = _finite(self.health_score, "health_score")
        risk = _finite(self.risk_score, "risk_score")
        if health > 1 or risk > 1:
            raise ProviderMetadataError("health_score and risk_score must be in [0,1]")
        object.__setattr__(self, "health_score", health)
        object.__setattr__(self, "risk_score", risk)
        observed = _finite(self.observed_at, "observed_at")
        expires = _finite(self.expires_at, "expires_at")
        if expires <= observed:
            raise ProviderMetadataError("expires_at must exceed observed_at")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "evidence", _evidence(self.evidence))
        object.__setattr__(self, "verifier_id", _token(self.verifier_id, "verifier_id"))
        object.__setattr__(
            self,
            "verifier_digest",
            _sha(self.verifier_digest, "verifier_digest"),
        )
        if self.independent is not True:
            raise ProviderMetadataError("route observation must be independently verified")
        if self.authority_scope != ROUTING_AUTHORITY_SCOPE:
            raise ProviderMetadataError("route observation cannot grant execution authority")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "provider_id": self.provider_id,
                "model": self.model,
                "health_score": self.health_score,
                "risk_score": self.risk_score,
                "observed_at": self.observed_at,
                "expires_at": self.expires_at,
                "evidence": [
                    {"source": e.source, "digest": e.digest, "category": e.category}
                    for e in self.evidence
                ],
                "verifier_id": self.verifier_id,
                "verifier_digest": self.verifier_digest,
                "authority_scope": self.authority_scope,
            }
        )


@dataclass(frozen=True, slots=True)
class RouteQualificationRequest:
    required_capabilities: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    min_health_score: float
    max_risk_score: float
    max_estimated_cost: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "required_capabilities",
            _tokens(self.required_capabilities, "required_capabilities"),
        )
        for field in ("input_tokens", "output_tokens"):
            value = getattr(self, field)
            floor = 0 if field == "input_tokens" else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < floor:
                raise ProviderMetadataError(f"{field} is invalid")
        health = _finite(self.min_health_score, "min_health_score")
        risk = _finite(self.max_risk_score, "max_risk_score")
        if health > 1 or risk > 1:
            raise ProviderMetadataError("health/risk thresholds must be in [0,1]")
        object.__setattr__(self, "min_health_score", health)
        object.__setattr__(self, "max_risk_score", risk)
        if self.max_estimated_cost is not None:
            object.__setattr__(
                self,
                "max_estimated_cost",
                _finite(self.max_estimated_cost, "max_estimated_cost"),
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "required_capabilities": list(self.required_capabilities),
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "min_health_score": self.min_health_score,
                "max_risk_score": self.max_risk_score,
                "max_estimated_cost": self.max_estimated_cost,
            }
        )


@dataclass(frozen=True, slots=True)
class RouteQualificationDecision:
    registry_digest: str
    request_digest: str
    selected_provider_id: str | None
    eligible_provider_ids: tuple[str, ...]
    rejected: tuple[tuple[str, tuple[str, ...]], ...]
    observation_digests: tuple[tuple[str, str], ...]
    observed_at: float
    authority_scope: str = ROUTING_AUTHORITY_SCOPE

    @property
    def digest(self) -> str:
        return _digest(
            {
                "registry_digest": self.registry_digest,
                "request_digest": self.request_digest,
                "selected_provider_id": self.selected_provider_id,
                "eligible_provider_ids": list(self.eligible_provider_ids),
                "rejected": [[key, list(reasons)] for key, reasons in self.rejected],
                "observation_digests": [list(item) for item in self.observation_digests],
                "observed_at": self.observed_at,
                "authority_scope": self.authority_scope,
            }
        )


def qualify_registry_routes(
    registry: RouterRegistry,
    request: RouteQualificationRequest,
    observations: Mapping[str, RouteObservation],
    *,
    observed_at: float,
    expected_registry_digest: str | None = None,
) -> RouteQualificationDecision:
    if not isinstance(registry, RouterRegistry):
        raise TypeError("registry must be RouterRegistry")
    if not isinstance(request, RouteQualificationRequest):
        raise TypeError("request must be RouteQualificationRequest")
    if not isinstance(observations, Mapping):
        raise TypeError("observations must be a mapping")

    now = _finite(observed_at, "observed_at")
    snapshot = registry.snapshot()
    if expected_registry_digest is not None:
        _sha(expected_registry_digest, "expected_registry_digest")
        if expected_registry_digest != snapshot.digest:
            raise ProviderMetadataError("stale router registry digest")

    accepted: list[tuple[tuple[float, float, float, float, str], str]] = []
    rejected: list[tuple[str, tuple[str, ...]]] = []
    observed: list[tuple[str, str]] = []

    for provider in snapshot.providers:
        reasons: list[str] = []
        observation = observations.get(provider.provider_id)
        if not provider.enabled:
            reasons.append("disabled")
        if not set(request.required_capabilities) <= set(provider.capabilities):
            reasons.append("capability-mismatch")
        if request.input_tokens > provider.max_input_tokens:
            reasons.append("input-capacity")
        if request.output_tokens > provider.max_output_tokens:
            reasons.append("output-capacity")

        health, risk = 0.0, 1.0
        if not isinstance(observation, RouteObservation):
            reasons.append("missing-route-observation")
        else:
            observed.append((provider.provider_id, observation.digest))
            health, risk = observation.health_score, observation.risk_score
            if observation.provider_id != provider.provider_id:
                reasons.append("observation-provider-mismatch")
            if observation.model != provider.model:
                reasons.append("observation-model-mismatch")
            if now < observation.observed_at:
                reasons.append("observation-not-yet-valid")
            if now >= observation.expires_at:
                reasons.append("observation-expired")
            if health < request.min_health_score:
                reasons.append("health-threshold")
            if risk > request.max_risk_score:
                reasons.append("risk-threshold")

        cost = (
            request.input_tokens * provider.input_cost_per_million
            + request.output_tokens * provider.output_cost_per_million
        ) / 1_000_000.0
        if request.max_estimated_cost is not None and cost > request.max_estimated_cost:
            reasons.append("cost-budget")

        if reasons:
            rejected.append((provider.provider_id, tuple(sorted(set(reasons)))))
        else:
            accepted.append(
                (
                    (float(provider.priority), risk, -health, cost, provider.provider_id),
                    provider.provider_id,
                )
            )

    accepted.sort(key=lambda item: item[0])
    rejected.sort(key=lambda item: item[0])
    observed.sort(key=lambda item: item[0])
    eligible = tuple(provider_id for _, provider_id in accepted)
    return RouteQualificationDecision(
        registry_digest=snapshot.digest,
        request_digest=request.digest,
        selected_provider_id=eligible[0] if eligible else None,
        eligible_provider_ids=eligible,
        rejected=tuple(rejected),
        observation_digests=tuple(observed),
        observed_at=now,
    )


__all__ = [
    "ROUTING_AUTHORITY_SCOPE",
    "ROUTING_GOVERNANCE_VERSION",
    "RouteObservation",
    "RouteQualificationDecision",
    "RouteQualificationRequest",
    "qualify_registry_routes",
]
