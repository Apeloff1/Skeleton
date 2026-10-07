"""Deterministic historical-model benchmark selection for Jeeves.

This module answers one narrow question: *given recorded benchmark evidence,
which model has the strongest historical record for a requested workload?*

It deliberately does not ask a live model to rate itself, scrape mutable
leaderboards, or silently convert provider marketing claims into capability.
All inputs are explicit historical observations with provenance. Selection is
repeatable, uncertainty-aware, workload-specific, and fail-closed when evidence
is incomplete.

The selector is provider-neutral. A model identity is a stable
(provider, model, revision) tuple; benchmark evidence can therefore compare
OpenAI, Anthropic, local, or future providers without coupling Jeeves to a
specific API.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from statistics import fmean
from typing import Final

from skeleton.kernel.errors import KernelError
from skeleton.learning.evidence import EvidenceProvenance, canonical_fingerprint


MAX_ID_CHARS: Final = 160
MAX_URI_CHARS: Final = 1_024
DEFAULT_MIN_SAMPLE_COUNT: Final = 32
DEFAULT_CONFIDENCE_Z: Final = 1.96
DEFAULT_MAX_SNAPSHOT_AGE_SECONDS: Final = 365.25 * 24 * 60 * 60 * 5
DEFAULT_MAX_SNAPSHOTS_PER_BENCHMARK: Final = 32
_EPSILON: Final = 1e-12


class HistoricalModelError(KernelError):
    """Fail-closed historical benchmark contract violation."""

    code = "JVS.HISTORICAL_MODEL"
    http_status = 422


class BenchmarkDomain(str, Enum):
    """Workload dimensions used by the selector."""

    REASONING = "reasoning"
    CODING = "coding"
    RESEARCH = "research"
    TOOL_USE = "tool_use"
    LONG_CONTEXT = "long_context"
    INSTRUCTION_FOLLOWING = "instruction_following"
    SAFETY = "safety"
    LATENCY = "latency"
    COST = "cost"


class MetricDirection(str, Enum):
    """Whether a larger raw benchmark number is desirable."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class MissingDomainPolicy(str, Enum):
    """How selection behaves when a model lacks a required domain."""

    REJECT = "reject"
    PENALIZE = "penalize"


def _bounded_text(name: str, value: object, maximum: int = MAX_ID_CHARS) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalModelError(
            f"{name} must be a non-empty string",
            context={"field": name, "reason": "invalid_text"},
        )
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise HistoricalModelError(
            f"{name} exceeds {maximum} characters",
            context={"field": name, "reason": "too_long", "max_chars": maximum},
        )
    return cleaned


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModelError(
            f"{name} must be numeric",
            context={"field": name, "reason": "invalid_number"},
        )
    number = float(value)
    if not math.isfinite(number):
        raise HistoricalModelError(
            f"{name} must be finite",
            context={"field": name, "reason": "invalid_number"},
        )
    return number


def _unit(name: str, value: object) -> float:
    number = _finite(name, value)
    if number < 0.0 or number > 1.0:
        raise HistoricalModelError(
            f"{name} must be between 0 and 1",
            context={"field": name, "reason": "out_of_range"},
        )
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalModelError(
            f"{name} must be a positive integer",
            context={"field": name, "reason": "invalid_integer"},
        )
    return value


@dataclass(frozen=True, slots=True, order=True)
class ModelIdentity:
    """Stable provider-neutral model identity."""

    provider: str
    model: str
    revision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _bounded_text("provider", self.provider).casefold())
        object.__setattr__(self, "model", _bounded_text("model", self.model))
        object.__setattr__(self, "revision", _bounded_text("revision", self.revision))

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}@{self.revision}"


@dataclass(frozen=True, slots=True)
class BenchmarkDefinition:
    """Immutable benchmark normalization contract.

    Raw measurements are normalized to [0, 1]. The declared bounds are part of
    the benchmark revision, preventing a later normalization change from
    retroactively rewriting old evidence.
    """

    benchmark_id: str
    revision: str
    domain: BenchmarkDomain
    raw_min: float
    raw_max: float
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER
    weight_hint: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "benchmark_id", _bounded_text("benchmark_id", self.benchmark_id))
        object.__setattr__(self, "revision", _bounded_text("benchmark revision", self.revision))
        if not isinstance(self.domain, BenchmarkDomain):
            raise HistoricalModelError("domain must be BenchmarkDomain", context={"reason": "invalid_domain"})
        if not isinstance(self.direction, MetricDirection):
            raise HistoricalModelError(
                "direction must be MetricDirection",
                context={"reason": "invalid_direction"},
            )
        raw_min = _finite("raw_min", self.raw_min)
        raw_max = _finite("raw_max", self.raw_max)
        if raw_max <= raw_min:
            raise HistoricalModelError(
                "raw_max must be greater than raw_min",
                context={"reason": "invalid_bounds"},
            )
        object.__setattr__(self, "raw_min", raw_min)
        object.__setattr__(self, "raw_max", raw_max)
        hint = _finite("weight_hint", self.weight_hint)
        if hint <= 0.0:
            raise HistoricalModelError(
                "weight_hint must be positive",
                context={"reason": "invalid_weight"},
            )
        object.__setattr__(self, "weight_hint", hint)

    @property
    def key(self) -> str:
        return f"{self.benchmark_id}@{self.revision}"

    def normalize(self, raw_score: float) -> float:
        raw = _finite("raw_score", raw_score)
        if raw < self.raw_min or raw > self.raw_max:
            raise HistoricalModelError(
                "raw_score is outside benchmark bounds",
                context={
                    "reason": "raw_score_out_of_bounds",
                    "benchmark": self.key,
                    "raw_score": raw,
                    "raw_min": self.raw_min,
                    "raw_max": self.raw_max,
                },
            )
        ratio = (raw - self.raw_min) / (self.raw_max - self.raw_min)
        if self.direction is MetricDirection.LOWER_IS_BETTER:
            ratio = 1.0 - ratio
        return min(1.0, max(0.0, ratio))


@dataclass(frozen=True, slots=True)
class BenchmarkSnapshot:
    """One historical benchmark observation for one model revision."""

    snapshot_id: str
    model: ModelIdentity
    benchmark: BenchmarkDefinition
    raw_score: float
    sample_count: int
    measured_at: float
    provenance: EvidenceProvenance
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _bounded_text("snapshot_id", self.snapshot_id))
        if not isinstance(self.model, ModelIdentity):
            raise HistoricalModelError("model must be ModelIdentity", context={"reason": "invalid_model"})
        if not isinstance(self.benchmark, BenchmarkDefinition):
            raise HistoricalModelError(
                "benchmark must be BenchmarkDefinition",
                context={"reason": "invalid_benchmark"},
            )
        raw = _finite("raw_score", self.raw_score)
        self.benchmark.normalize(raw)
        object.__setattr__(self, "raw_score", raw)
        object.__setattr__(self, "sample_count", _positive_int("sample_count", self.sample_count))
        measured = _finite("measured_at", self.measured_at)
        if measured < 0.0:
            raise HistoricalModelError(
                "measured_at must be non-negative",
                context={"reason": "invalid_timestamp"},
            )
        object.__setattr__(self, "measured_at", measured)
        if not isinstance(self.provenance, EvidenceProvenance):
            raise HistoricalModelError(
                "benchmark provenance is required",
                context={"reason": "missing_provenance"},
            )
        if self.provenance.observed_at != measured:
            raise HistoricalModelError(
                "provenance observed_at must equal measured_at",
                context={"reason": "timestamp_mismatch", "snapshot_id": self.snapshot_id},
            )
        expected = canonical_fingerprint(self.fingerprint_payload())
        if self.provenance.fingerprint != expected:
            raise HistoricalModelError(
                "benchmark provenance fingerprint does not match snapshot",
                context={"reason": "fingerprint_mismatch", "snapshot_id": self.snapshot_id},
            )
        if self.notes:
            object.__setattr__(self, "notes", _bounded_text("notes", self.notes, 2_048))

    @property
    def normalized_score(self) -> float:
        return self.benchmark.normalize(self.raw_score)

    def fingerprint_payload(self) -> Mapping[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "model": self.model.key,
            "benchmark": self.benchmark.key,
            "domain": self.benchmark.domain.value,
            "raw_score": self.raw_score,
            "sample_count": self.sample_count,
            "measured_at": self.measured_at,
        }


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    """Workload-specific champion selection policy."""

    domain_weights: Mapping[BenchmarkDomain, float]
    required_domains: frozenset[BenchmarkDomain] = frozenset()
    minimum_sample_count: int = DEFAULT_MIN_SAMPLE_COUNT
    confidence_z: float = DEFAULT_CONFIDENCE_Z
    max_snapshot_age_seconds: float = DEFAULT_MAX_SNAPSHOT_AGE_SECONDS
    missing_domain_policy: MissingDomainPolicy = MissingDomainPolicy.REJECT
    missing_domain_score: float = 0.0
    recency_half_life_seconds: float | None = None

    def __post_init__(self) -> None:
        if not self.domain_weights:
            raise HistoricalModelError(
                "domain_weights must not be empty",
                context={"reason": "empty_policy"},
            )
        clean: dict[BenchmarkDomain, float] = {}
        for domain, weight in self.domain_weights.items():
            if not isinstance(domain, BenchmarkDomain):
                raise HistoricalModelError(
                    "domain weight key must be BenchmarkDomain",
                    context={"reason": "invalid_domain"},
                )
            numeric = _finite(f"weight[{domain.value}]", weight)
            if numeric <= 0.0:
                raise HistoricalModelError(
                    "domain weights must be positive",
                    context={"reason": "invalid_weight", "domain": domain.value},
                )
            clean[domain] = numeric
        object.__setattr__(self, "domain_weights", clean)
        if not isinstance(self.required_domains, frozenset):
            object.__setattr__(self, "required_domains", frozenset(self.required_domains))
        unknown_required = [d for d in self.required_domains if not isinstance(d, BenchmarkDomain)]
        if unknown_required:
            raise HistoricalModelError(
                "required_domains must contain BenchmarkDomain values",
                context={"reason": "invalid_domain"},
            )
        if not self.required_domains.issubset(clean):
            raise HistoricalModelError(
                "required_domains must also have domain weights",
                context={"reason": "missing_weight"},
            )
        object.__setattr__(self, "minimum_sample_count", _positive_int("minimum_sample_count", self.minimum_sample_count))
        z = _finite("confidence_z", self.confidence_z)
        if z < 0.0 or z > 8.0:
            raise HistoricalModelError("confidence_z must be between 0 and 8", context={"reason": "invalid_confidence_z"})
        object.__setattr__(self, "confidence_z", z)
        age = _finite("max_snapshot_age_seconds", self.max_snapshot_age_seconds)
        if age <= 0.0:
            raise HistoricalModelError(
                "max_snapshot_age_seconds must be positive",
                context={"reason": "invalid_age"},
            )
        object.__setattr__(self, "max_snapshot_age_seconds", age)
        if not isinstance(self.missing_domain_policy, MissingDomainPolicy):
            raise HistoricalModelError(
                "missing_domain_policy must be MissingDomainPolicy",
                context={"reason": "invalid_missing_domain_policy"},
            )
        object.__setattr__(self, "missing_domain_score", _unit("missing_domain_score", self.missing_domain_score))
        if self.recency_half_life_seconds is not None:
            half_life = _finite("recency_half_life_seconds", self.recency_half_life_seconds)
            if half_life <= 0.0:
                raise HistoricalModelError(
                    "recency_half_life_seconds must be positive",
                    context={"reason": "invalid_half_life"},
                )
            object.__setattr__(self, "recency_half_life_seconds", half_life)

    @property
    def normalized_weights(self) -> Mapping[BenchmarkDomain, float]:
        total = sum(self.domain_weights.values())
        return {domain: weight / total for domain, weight in self.domain_weights.items()}


@dataclass(frozen=True, slots=True)
class DomainScore:
    domain: BenchmarkDomain
    score: float
    conservative_score: float
    effective_samples: int
    snapshot_ids: tuple[str, ...]
    newest_measured_at: float


@dataclass(frozen=True, slots=True)
class ModelScore:
    model: ModelIdentity
    score: float
    conservative_score: float
    coverage: float
    effective_samples: int
    domains: tuple[DomainScore, ...]
    missing_domains: tuple[BenchmarkDomain, ...] = ()

    @property
    def percent(self) -> float:
        return round(self.conservative_score * 100.0, 2)


@dataclass(frozen=True, slots=True)
class ChampionDecision:
    """Deterministic champion decision and complete evidence trail."""

    champion: ModelScore
    candidates: tuple[ModelScore, ...]
    evaluated_at: float
    policy_fingerprint: str
    evidence_fingerprint: str

    @property
    def historical_best_percent(self) -> float:
        return self.champion.percent


@dataclass(slots=True)
class HistoricalModelRegistry:
    """Append-only historical benchmark registry with deterministic selection."""

    clock: callable
    max_snapshots_per_benchmark: int = DEFAULT_MAX_SNAPSHOTS_PER_BENCHMARK
    _snapshots: dict[str, BenchmarkSnapshot] = field(default_factory=dict, init=False)
    _logical_keys: dict[tuple[str, str, float], str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if not callable(self.clock):
            raise HistoricalModelError("clock must be callable", context={"reason": "invalid_clock"})
        self.max_snapshots_per_benchmark = _positive_int(
            "max_snapshots_per_benchmark",
            self.max_snapshots_per_benchmark,
        )

    def ingest(self, snapshot: BenchmarkSnapshot) -> None:
        if not isinstance(snapshot, BenchmarkSnapshot):
            raise HistoricalModelError(
                "snapshot must be BenchmarkSnapshot",
                context={"reason": "invalid_snapshot"},
            )
        now = _finite("clock()", self.clock())
        if snapshot.measured_at > now + _EPSILON:
            raise HistoricalModelError(
                "future benchmark snapshots are rejected",
                context={"reason": "future_snapshot", "snapshot_id": snapshot.snapshot_id},
            )
        if snapshot.snapshot_id in self._snapshots:
            existing = self._snapshots[snapshot.snapshot_id]
            if existing == snapshot:
                return
            raise HistoricalModelError(
                "snapshot_id already exists with different content",
                context={"reason": "duplicate_snapshot", "snapshot_id": snapshot.snapshot_id},
            )
        logical_key = (snapshot.model.key, snapshot.benchmark.key, snapshot.measured_at)
        prior_id = self._logical_keys.get(logical_key)
        if prior_id is not None:
            prior = self._snapshots[prior_id]
            if prior.raw_score != snapshot.raw_score or prior.sample_count != snapshot.sample_count:
                raise HistoricalModelError(
                    "conflicting benchmark snapshots at the same model/benchmark/time",
                    context={"reason": "contradictory_snapshot", "prior_id": prior_id},
                )
            return
        siblings = [
            item
            for item in self._snapshots.values()
            if item.model == snapshot.model and item.benchmark.key == snapshot.benchmark.key
        ]
        if len(siblings) >= self.max_snapshots_per_benchmark:
            raise HistoricalModelError(
                "snapshot history limit reached for model benchmark",
                context={
                    "reason": "history_limit",
                    "model": snapshot.model.key,
                    "benchmark": snapshot.benchmark.key,
                    "max_snapshots": self.max_snapshots_per_benchmark,
                },
            )
        self._snapshots[snapshot.snapshot_id] = snapshot
        self._logical_keys[logical_key] = snapshot.snapshot_id

    def snapshots(self) -> tuple[BenchmarkSnapshot, ...]:
        return tuple(
            sorted(
                self._snapshots.values(),
                key=lambda item: (item.measured_at, item.snapshot_id),
            )
        )

    def models(self) -> tuple[ModelIdentity, ...]:
        return tuple(sorted({snapshot.model for snapshot in self._snapshots.values()}))

    def snapshots_for(self, model: ModelIdentity) -> tuple[BenchmarkSnapshot, ...]:
        return tuple(snapshot for snapshot in self.snapshots() if snapshot.model == model)

    def select_champion(
        self,
        policy: SelectionPolicy,
        *,
        models: Iterable[ModelIdentity] | None = None,
    ) -> ChampionDecision:
        if not isinstance(policy, SelectionPolicy):
            raise HistoricalModelError("policy must be SelectionPolicy", context={"reason": "invalid_policy"})
        now = _finite("clock()", self.clock())
        requested = tuple(sorted(set(models))) if models is not None else self.models()
        if not requested:
            raise HistoricalModelError("no models available for selection", context={"reason": "no_candidates"})

        candidates: list[ModelScore] = []
        rejection_reasons: dict[str, str] = {}
        for model in requested:
            if not isinstance(model, ModelIdentity):
                raise HistoricalModelError("models must contain ModelIdentity", context={"reason": "invalid_model"})
            try:
                candidates.append(self._score_model(model, policy, now=now))
            except HistoricalModelError as exc:
                rejection_reasons[model.key] = str(exc)

        if not candidates:
            raise HistoricalModelError(
                "no candidate satisfied the historical evidence policy",
                context={"reason": "no_eligible_candidates", "rejections": rejection_reasons},
            )

        ranked = tuple(
            sorted(
                candidates,
                key=lambda item: (
                    -item.conservative_score,
                    -item.score,
                    -item.coverage,
                    -item.effective_samples,
                    item.model.key,
                ),
            )
        )
        evidence_ids = sorted(
            snapshot.snapshot_id
            for snapshot in self._snapshots.values()
            if snapshot.model in {candidate.model for candidate in ranked}
        )
        return ChampionDecision(
            champion=ranked[0],
            candidates=ranked,
            evaluated_at=now,
            policy_fingerprint=canonical_fingerprint(self._policy_payload(policy)),
            evidence_fingerprint=canonical_fingerprint(evidence_ids),
        )

    def _score_model(self, model: ModelIdentity, policy: SelectionPolicy, *, now: float) -> ModelScore:
        usable = [
            snapshot
            for snapshot in self._snapshots.values()
            if snapshot.model == model
            and snapshot.sample_count >= policy.minimum_sample_count
            and 0.0 <= now - snapshot.measured_at <= policy.max_snapshot_age_seconds
        ]
        if not usable:
            raise HistoricalModelError(
                "model has no fresh benchmark evidence",
                context={"reason": "no_fresh_evidence", "model": model.key},
            )

        by_domain: dict[BenchmarkDomain, list[BenchmarkSnapshot]] = defaultdict(list)
        for snapshot in usable:
            if snapshot.benchmark.domain in policy.domain_weights:
                by_domain[snapshot.benchmark.domain].append(snapshot)

        weighted_score = 0.0
        weighted_conservative = 0.0
        coverage = 0.0
        effective_samples = 0
        domain_scores: list[DomainScore] = []
        missing: list[BenchmarkDomain] = []

        for domain, weight in policy.normalized_weights.items():
            domain_snapshots = by_domain.get(domain, [])
            if not domain_snapshots:
                missing.append(domain)
                if domain in policy.required_domains or policy.missing_domain_policy is MissingDomainPolicy.REJECT:
                    continue
                weighted_score += weight * policy.missing_domain_score
                weighted_conservative += weight * policy.missing_domain_score
                continue

            domain_score = self._score_domain(domain, domain_snapshots, policy, now=now)
            domain_scores.append(domain_score)
            weighted_score += weight * domain_score.score
            weighted_conservative += weight * domain_score.conservative_score
            coverage += weight
            effective_samples += domain_score.effective_samples

        blocking = [domain for domain in missing if domain in policy.required_domains]
        if blocking:
            raise HistoricalModelError(
                "model is missing required benchmark domains",
                context={
                    "reason": "missing_required_domain",
                    "model": model.key,
                    "domains": [domain.value for domain in blocking],
                },
            )
        if missing and policy.missing_domain_policy is MissingDomainPolicy.REJECT:
            raise HistoricalModelError(
                "model is missing benchmark domains",
                context={
                    "reason": "missing_domain",
                    "model": model.key,
                    "domains": [domain.value for domain in missing],
                },
            )
        if not domain_scores and coverage <= 0.0:
            raise HistoricalModelError(
                "model has no evidence for policy domains",
                context={"reason": "no_policy_evidence", "model": model.key},
            )

        return ModelScore(
            model=model,
            score=min(1.0, max(0.0, weighted_score)),
            conservative_score=min(1.0, max(0.0, weighted_conservative)),
            coverage=min(1.0, max(0.0, coverage)),
            effective_samples=effective_samples,
            domains=tuple(sorted(domain_scores, key=lambda item: item.domain.value)),
            missing_domains=tuple(sorted(missing, key=lambda item: item.value)),
        )

    def _score_domain(
        self,
        domain: BenchmarkDomain,
        snapshots: list[BenchmarkSnapshot],
        policy: SelectionPolicy,
        *,
        now: float,
    ) -> DomainScore:
        weighted: list[tuple[float, float, int, BenchmarkSnapshot]] = []
        for snapshot in snapshots:
            age = max(0.0, now - snapshot.measured_at)
            recency = 1.0
            if policy.recency_half_life_seconds is not None:
                recency = math.pow(0.5, age / policy.recency_half_life_seconds)
            evidence_weight = float(snapshot.sample_count) * snapshot.benchmark.weight_hint * recency
            weighted.append((snapshot.normalized_score, evidence_weight, snapshot.sample_count, snapshot))

        total_weight = sum(item[1] for item in weighted)
        if total_weight <= _EPSILON:
            raise HistoricalModelError(
                "domain evidence has zero effective weight",
                context={"reason": "zero_weight", "domain": domain.value},
            )
        score = sum(value * weight for value, weight, _, _ in weighted) / total_weight
        sample_count = sum(samples for _, _, samples, _ in weighted)
        conservative = self._wilson_lower_bound(score, sample_count, policy.confidence_z)
        newest = max(item[3].measured_at for item in weighted)
        return DomainScore(
            domain=domain,
            score=score,
            conservative_score=conservative,
            effective_samples=sample_count,
            snapshot_ids=tuple(sorted(item[3].snapshot_id for item in weighted)),
            newest_measured_at=newest,
        )

    @staticmethod
    def _wilson_lower_bound(rate: float, samples: int, z: float) -> float:
        """Conservative lower confidence bound for a normalized score.

        Historical benchmark scores are not necessarily Bernoulli outcomes, so
        this is used as a deterministic uncertainty penalty rather than a claim
        that every benchmark literally follows a binomial distribution.
        """
        rate = _unit("rate", rate)
        samples = _positive_int("samples", samples)
        if z == 0.0:
            return rate
        z2 = z * z
        denominator = 1.0 + z2 / samples
        centre = rate + z2 / (2.0 * samples)
        margin = z * math.sqrt((rate * (1.0 - rate) + z2 / (4.0 * samples)) / samples)
        return min(1.0, max(0.0, (centre - margin) / denominator))

    @staticmethod
    def _policy_payload(policy: SelectionPolicy) -> Mapping[str, object]:
        return {
            "domain_weights": {
                domain.value: weight
                for domain, weight in sorted(policy.domain_weights.items(), key=lambda item: item[0].value)
            },
            "required_domains": sorted(domain.value for domain in policy.required_domains),
            "minimum_sample_count": policy.minimum_sample_count,
            "confidence_z": policy.confidence_z,
            "max_snapshot_age_seconds": policy.max_snapshot_age_seconds,
            "missing_domain_policy": policy.missing_domain_policy.value,
            "missing_domain_score": policy.missing_domain_score,
            "recency_half_life_seconds": policy.recency_half_life_seconds,
        }


def make_benchmark_provenance(
    *,
    source_id: str,
    source_kind: str,
    measured_at: float,
    clock_version: int,
    snapshot_id: str,
    model: ModelIdentity,
    benchmark: BenchmarkDefinition,
    raw_score: float,
    sample_count: int,
    uri: str | None = None,
) -> EvidenceProvenance:
    """Create canonical provenance for a benchmark snapshot.

    This helper prevents callers from hand-rolling a fingerprint differently
    from :class:`BenchmarkSnapshot`.
    """
    payload = {
        "snapshot_id": _bounded_text("snapshot_id", snapshot_id),
        "model": model.key,
        "benchmark": benchmark.key,
        "domain": benchmark.domain.value,
        "raw_score": _finite("raw_score", raw_score),
        "sample_count": _positive_int("sample_count", sample_count),
        "measured_at": _finite("measured_at", measured_at),
    }
    if uri is not None:
        uri = _bounded_text("uri", uri, MAX_URI_CHARS)
    return EvidenceProvenance(
        source_id=source_id,
        source_kind=source_kind,
        observed_at=payload["measured_at"],
        clock_version=clock_version,
        fingerprint=canonical_fingerprint(payload),
        uri=uri,
    )


def balanced_frontier_policy() -> SelectionPolicy:
    """Conservative general-purpose workload policy for Jeeves.

    It intentionally weights reasoning, coding, research, tool use, and
    instruction following most heavily while keeping long-context and safety in
    the decision. Cost and latency remain available as workload-specific
    dimensions rather than silently dominating quality selection.
    """
    return SelectionPolicy(
        domain_weights={
            BenchmarkDomain.REASONING: 1.35,
            BenchmarkDomain.CODING: 1.25,
            BenchmarkDomain.RESEARCH: 1.15,
            BenchmarkDomain.TOOL_USE: 1.10,
            BenchmarkDomain.INSTRUCTION_FOLLOWING: 1.10,
            BenchmarkDomain.LONG_CONTEXT: 0.90,
            BenchmarkDomain.SAFETY: 0.90,
        },
        required_domains=frozenset(
            {
                BenchmarkDomain.REASONING,
                BenchmarkDomain.CODING,
                BenchmarkDomain.INSTRUCTION_FOLLOWING,
            }
        ),
        minimum_sample_count=DEFAULT_MIN_SAMPLE_COUNT,
        confidence_z=DEFAULT_CONFIDENCE_Z,
        missing_domain_policy=MissingDomainPolicy.PENALIZE,
        missing_domain_score=0.0,
    )


def summarize_decision(decision: ChampionDecision) -> Mapping[str, object]:
    """JSON-friendly summary suitable for logs, evidence, and UI surfaces."""
    return {
        "historical_champion": decision.champion.model.key,
        "historical_best_percent": decision.historical_best_percent,
        "score": decision.champion.score,
        "conservative_score": decision.champion.conservative_score,
        "coverage": decision.champion.coverage,
        "effective_samples": decision.champion.effective_samples,
        "evaluated_at": decision.evaluated_at,
        "policy_fingerprint": decision.policy_fingerprint,
        "evidence_fingerprint": decision.evidence_fingerprint,
        "domains": [
            {
                "domain": item.domain.value,
                "score": item.score,
                "conservative_score": item.conservative_score,
                "effective_samples": item.effective_samples,
                "snapshot_ids": list(item.snapshot_ids),
                "newest_measured_at": item.newest_measured_at,
            }
            for item in decision.champion.domains
        ],
    }