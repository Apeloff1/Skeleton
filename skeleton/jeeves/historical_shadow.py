"""Paired shadow-evaluation evidence for Jeeves historical challengers.

Shadow evidence compares an incumbent and challenger on the same externally
scored workload slice before any activation occurs. This module stores only
explicit caller-provided measurements with provenance; it never invokes models,
routes production traffic, or learns from live model output automatically.

The report uses paired score differences, weighted by declared sample counts,
plus a transparent observation-level uncertainty penalty. It is an additional
diagnostic, not a replacement for holdout, backtest, independence, or lineage
checks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

from skeleton.jeeves.historical_models import BenchmarkDomain, ModelIdentity, canonical_fingerprint
from skeleton.learning.evidence import EvidenceProvenance


DEFAULT_MAX_SHADOW_OBSERVATIONS: Final = 10_000
DEFAULT_MAX_AGE_SECONDS: Final = 180.0 * 24 * 60 * 60
_EPSILON: Final = 1e-12


class HistoricalShadowError(ValueError):
    """Invalid shadow evidence or evaluation contract."""


def _text(name: str, value: object, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalShadowError(f"{name} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise HistoricalShadowError(f"{name} exceeds {maximum} characters")
    return cleaned


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalShadowError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise HistoricalShadowError(f"{name} must be finite")
    return number


def _unit(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise HistoricalShadowError(f"{name} must be between 0 and 1")
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalShadowError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    observation_id: str
    incumbent: ModelIdentity
    challenger: ModelIdentity
    domain: BenchmarkDomain
    incumbent_score: float
    challenger_score: float
    sample_count: int
    measured_at: float
    provenance: EvidenceProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _text("observation_id", self.observation_id, 160))
        if not isinstance(self.incumbent, ModelIdentity) or not isinstance(self.challenger, ModelIdentity):
            raise HistoricalShadowError("incumbent and challenger must be ModelIdentity values")
        if self.incumbent == self.challenger:
            raise HistoricalShadowError("shadow comparison requires distinct models")
        if not isinstance(self.domain, BenchmarkDomain):
            raise HistoricalShadowError("domain must be BenchmarkDomain")
        object.__setattr__(self, "incumbent_score", _unit("incumbent_score", self.incumbent_score))
        object.__setattr__(self, "challenger_score", _unit("challenger_score", self.challenger_score))
        object.__setattr__(self, "sample_count", _positive_int("sample_count", self.sample_count))
        measured_at = _finite("measured_at", self.measured_at)
        if measured_at < 0.0:
            raise HistoricalShadowError("measured_at must be non-negative")
        object.__setattr__(self, "measured_at", measured_at)
        if not isinstance(self.provenance, EvidenceProvenance):
            raise HistoricalShadowError("shadow observation provenance is required")
        if self.provenance.observed_at != measured_at:
            raise HistoricalShadowError("shadow provenance timestamp mismatch")
        expected = canonical_fingerprint(self.fingerprint_payload())
        if self.provenance.fingerprint != expected:
            raise HistoricalShadowError("shadow provenance fingerprint mismatch")

    @property
    def advantage(self) -> float:
        return self.challenger_score - self.incumbent_score

    def fingerprint_payload(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "incumbent": self.incumbent.key,
            "challenger": self.challenger.key,
            "domain": self.domain.value,
            "incumbent_score": self.incumbent_score,
            "challenger_score": self.challenger_score,
            "sample_count": self.sample_count,
            "measured_at": self.measured_at,
        }


@dataclass(frozen=True, slots=True)
class ShadowPolicy:
    min_observations: int = 3
    min_total_samples: int = 128
    min_mean_advantage: float = 0.01
    min_conservative_advantage: float = 0.0
    max_loss_rate: float = 0.40
    confidence_z: float = 1.96
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(self, "min_observations", _positive_int("min_observations", self.min_observations))
        object.__setattr__(self, "min_total_samples", _positive_int("min_total_samples", self.min_total_samples))
        for name in ("min_mean_advantage", "min_conservative_advantage"):
            value = _finite(name, getattr(self, name))
            if not -1.0 <= value <= 1.0:
                raise HistoricalShadowError(f"{name} must be between -1 and 1")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "max_loss_rate", _unit("max_loss_rate", self.max_loss_rate))
        z = _finite("confidence_z", self.confidence_z)
        if z < 0.0 or z > 8.0:
            raise HistoricalShadowError("confidence_z must be between 0 and 8")
        object.__setattr__(self, "confidence_z", z)
        age = _finite("max_age_seconds", self.max_age_seconds)
        if age <= 0.0:
            raise HistoricalShadowError("max_age_seconds must be positive")
        object.__setattr__(self, "max_age_seconds", age)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "min_observations": self.min_observations,
                "min_total_samples": self.min_total_samples,
                "min_mean_advantage": self.min_mean_advantage,
                "min_conservative_advantage": self.min_conservative_advantage,
                "max_loss_rate": self.max_loss_rate,
                "confidence_z": self.confidence_z,
                "max_age_seconds": self.max_age_seconds,
            }
        )


@dataclass(frozen=True, slots=True)
class ShadowDomainResult:
    domain: BenchmarkDomain
    observations: int
    samples: int
    mean_advantage: float
    conservative_advantage: float
    win_rate: float
    loss_rate: float
    tie_rate: float
    observation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ShadowEvaluationReport:
    incumbent: ModelIdentity
    challenger: ModelIdentity
    observation_count: int
    total_samples: int
    mean_advantage: float
    conservative_advantage: float
    win_rate: float
    loss_rate: float
    domains: tuple[ShadowDomainResult, ...]
    reasons: tuple[str, ...]
    passed: bool
    policy_fingerprint: str
    evidence_fingerprint: str
    report_fingerprint: str


@dataclass(slots=True)
class HistoricalShadowLedger:
    clock: callable
    max_observations: int = DEFAULT_MAX_SHADOW_OBSERVATIONS
    _observations: dict[str, ShadowObservation] = field(default_factory=dict, init=False)
    _logical_keys: dict[tuple[str, str, str, float], str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if not callable(self.clock):
            raise HistoricalShadowError("clock must be callable")
        self.max_observations = _positive_int("max_observations", self.max_observations)

    def ingest(self, observation: ShadowObservation) -> None:
        if not isinstance(observation, ShadowObservation):
            raise HistoricalShadowError("observation must be ShadowObservation")
        now = _finite("clock()", self.clock())
        if observation.measured_at > now + _EPSILON:
            raise HistoricalShadowError("future shadow observations are rejected")
        existing = self._observations.get(observation.observation_id)
        if existing is not None:
            if existing == observation:
                return
            raise HistoricalShadowError("shadow observation id already exists with different content")
        logical = (
            observation.incumbent.key,
            observation.challenger.key,
            observation.domain.value,
            observation.measured_at,
        )
        prior_id = self._logical_keys.get(logical)
        if prior_id is not None:
            prior = self._observations[prior_id]
            if (
                prior.incumbent_score != observation.incumbent_score
                or prior.challenger_score != observation.challenger_score
                or prior.sample_count != observation.sample_count
            ):
                raise HistoricalShadowError("contradictory paired shadow observation")
            return
        if len(self._observations) >= self.max_observations:
            raise HistoricalShadowError("shadow ledger observation limit reached")
        self._observations[observation.observation_id] = observation
        self._logical_keys[logical] = observation.observation_id

    def observations(self) -> tuple[ShadowObservation, ...]:
        return tuple(sorted(self._observations.values(), key=lambda item: (item.measured_at, item.observation_id)))

    def evaluate(
        self,
        *,
        incumbent: ModelIdentity,
        challenger: ModelIdentity,
        policy: ShadowPolicy | None = None,
        domains: frozenset[BenchmarkDomain] | None = None,
    ) -> ShadowEvaluationReport:
        if not isinstance(incumbent, ModelIdentity) or not isinstance(challenger, ModelIdentity):
            raise HistoricalShadowError("incumbent and challenger must be ModelIdentity values")
        if incumbent == challenger:
            raise HistoricalShadowError("shadow evaluation requires distinct models")
        policy = policy or ShadowPolicy()
        if not isinstance(policy, ShadowPolicy):
            raise HistoricalShadowError("policy must be ShadowPolicy")
        if domains is not None:
            domains = frozenset(domains)
            if not domains or any(not isinstance(domain, BenchmarkDomain) for domain in domains):
                raise HistoricalShadowError("domains must be a non-empty set of BenchmarkDomain values")

        now = _finite("clock()", self.clock())
        selected = [
            item
            for item in self._observations.values()
            if item.incumbent == incumbent
            and item.challenger == challenger
            and 0.0 <= now - item.measured_at <= policy.max_age_seconds
            and (domains is None or item.domain in domains)
        ]
        if not selected:
            raise HistoricalShadowError("no fresh paired shadow evidence for requested models")
        selected.sort(key=lambda item: (item.measured_at, item.observation_id))

        total_samples = sum(item.sample_count for item in selected)
        weighted_advantage = sum(item.advantage * item.sample_count for item in selected) / total_samples
        advantages = [item.advantage for item in selected]
        mean_unweighted = sum(advantages) / len(advantages)
        if len(advantages) <= 1:
            standard_error = 0.0
        else:
            variance = sum((value - mean_unweighted) ** 2 for value in advantages) / (len(advantages) - 1)
            standard_error = math.sqrt(max(0.0, variance) / len(advantages))
        conservative = max(-1.0, min(1.0, weighted_advantage - policy.confidence_z * standard_error))
        wins = sum(1 for item in selected if item.advantage > _EPSILON)
        losses = sum(1 for item in selected if item.advantage < -_EPSILON)
        ties = len(selected) - wins - losses
        win_rate = wins / len(selected)
        loss_rate = losses / len(selected)

        by_domain: dict[BenchmarkDomain, list[ShadowObservation]] = {}
        for item in selected:
            by_domain.setdefault(item.domain, []).append(item)
        domain_results = tuple(
            self._domain_result(domain, items, policy)
            for domain, items in sorted(by_domain.items(), key=lambda pair: pair[0].value)
        )

        reasons: list[str] = []
        if len(selected) < policy.min_observations:
            reasons.append("insufficient_observations")
        if total_samples < policy.min_total_samples:
            reasons.append("insufficient_samples")
        if weighted_advantage + _EPSILON < policy.min_mean_advantage:
            reasons.append("insufficient_mean_advantage")
        if conservative + _EPSILON < policy.min_conservative_advantage:
            reasons.append("insufficient_conservative_advantage")
        if loss_rate > policy.max_loss_rate + _EPSILON:
            reasons.append("excessive_loss_rate")

        evidence_ids = tuple(item.observation_id for item in selected)
        evidence_fingerprint = canonical_fingerprint(evidence_ids)
        reason_tuple = tuple(sorted(reasons))
        payload = {
            "incumbent": incumbent.key,
            "challenger": challenger.key,
            "observations": evidence_ids,
            "mean_advantage": weighted_advantage,
            "conservative_advantage": conservative,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "reasons": list(reason_tuple),
            "policy": policy.fingerprint,
            "evidence": evidence_fingerprint,
        }
        return ShadowEvaluationReport(
            incumbent=incumbent,
            challenger=challenger,
            observation_count=len(selected),
            total_samples=total_samples,
            mean_advantage=weighted_advantage,
            conservative_advantage=conservative,
            win_rate=win_rate,
            loss_rate=loss_rate,
            domains=domain_results,
            reasons=reason_tuple,
            passed=not reason_tuple,
            policy_fingerprint=policy.fingerprint,
            evidence_fingerprint=evidence_fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )

    @staticmethod
    def _domain_result(
        domain: BenchmarkDomain,
        items: list[ShadowObservation],
        policy: ShadowPolicy,
    ) -> ShadowDomainResult:
        total_samples = sum(item.sample_count for item in items)
        weighted = sum(item.advantage * item.sample_count for item in items) / total_samples
        advantages = [item.advantage for item in items]
        mean = sum(advantages) / len(advantages)
        if len(items) <= 1:
            standard_error = 0.0
        else:
            variance = sum((value - mean) ** 2 for value in advantages) / (len(items) - 1)
            standard_error = math.sqrt(max(0.0, variance) / len(items))
        conservative = max(-1.0, min(1.0, weighted - policy.confidence_z * standard_error))
        wins = sum(1 for item in items if item.advantage > _EPSILON)
        losses = sum(1 for item in items if item.advantage < -_EPSILON)
        ties = len(items) - wins - losses
        return ShadowDomainResult(
            domain=domain,
            observations=len(items),
            samples=total_samples,
            mean_advantage=weighted,
            conservative_advantage=conservative,
            win_rate=wins / len(items),
            loss_rate=losses / len(items),
            tie_rate=ties / len(items),
            observation_ids=tuple(item.observation_id for item in items),
        )


def make_shadow_provenance(
    *,
    source_id: str,
    source_kind: str,
    observation_id: str,
    incumbent: ModelIdentity,
    challenger: ModelIdentity,
    domain: BenchmarkDomain,
    incumbent_score: float,
    challenger_score: float,
    sample_count: int,
    measured_at: float,
    clock_version: int,
    uri: str | None = None,
) -> EvidenceProvenance:
    payload = {
        "observation_id": _text("observation_id", observation_id, 160),
        "incumbent": incumbent.key,
        "challenger": challenger.key,
        "domain": domain.value,
        "incumbent_score": _unit("incumbent_score", incumbent_score),
        "challenger_score": _unit("challenger_score", challenger_score),
        "sample_count": _positive_int("sample_count", sample_count),
        "measured_at": _finite("measured_at", measured_at),
    }
    return EvidenceProvenance(
        source_id=source_id,
        source_kind=source_kind,
        observed_at=float(payload["measured_at"]),
        clock_version=clock_version,
        fingerprint=canonical_fingerprint(payload),
        uri=uri,
    )


def summarize_shadow(report: ShadowEvaluationReport) -> dict[str, object]:
    return {
        "incumbent": report.incumbent.key,
        "challenger": report.challenger.key,
        "passed": report.passed,
        "observation_count": report.observation_count,
        "total_samples": report.total_samples,
        "mean_advantage": report.mean_advantage,
        "conservative_advantage": report.conservative_advantage,
        "win_rate": report.win_rate,
        "loss_rate": report.loss_rate,
        "reasons": list(report.reasons),
        "policy_fingerprint": report.policy_fingerprint,
        "evidence_fingerprint": report.evidence_fingerprint,
        "report_fingerprint": report.report_fingerprint,
        "domains": [
            {
                "domain": item.domain.value,
                "observations": item.observations,
                "samples": item.samples,
                "mean_advantage": item.mean_advantage,
                "conservative_advantage": item.conservative_advantage,
                "win_rate": item.win_rate,
                "loss_rate": item.loss_rate,
                "tie_rate": item.tie_rate,
                "observation_ids": list(item.observation_ids),
            }
            for item in report.domains
        ],
    }