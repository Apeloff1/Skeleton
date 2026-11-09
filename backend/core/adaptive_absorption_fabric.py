"""Adaptive, orthogonal absorption fabric for Jeeves.

This module keeps knowledge acquisition off the serving critical path while letting
multiple bounded ingestion policies evolve rapidly in shadow.  Evolution is
aggressive only inside a non-evolvable safety envelope: challengers may change
routing, budgets and scoring weights, but they cannot weaken provenance,
verification, contradiction, rollback or serving-isolation constraints.

The implementation is deliberately pure and deterministic.  Durable queues,
workers and knowledge stores can call this policy layer without importing a DB or
provider runtime, which keeps it replayable and straightforward to test.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import hashlib
import math
from typing import Iterable, Mapping, Sequence

from core.evolution_policy import Direction, EvolutionCandidate, EvolutionPolicy, MetricSpec


class AbsorbLane(StrEnum):
    FAST = "fast"
    DEEP = "deep"
    ADVERSARIAL = "adversarial"
    SPECULATIVE = "speculative"
    REFRESH = "refresh"
    GAP = "gap"


class ClaimStage(StrEnum):
    RAW = "raw"
    NORMALIZED = "normalized"
    CLAIMED = "claimed"
    VERIFIED = "verified"
    CONTESTED = "contested"
    CANDIDATE = "candidate"
    PROMOTED = "promoted"
    QUARANTINED = "quarantined"
    REVOKED = "revoked"


class GenerationRole(StrEnum):
    CHAMPION = "champion"
    CHALLENGER = "challenger"
    ARCHIVED = "archived"


_TRANSITIONS: Mapping[ClaimStage, frozenset[ClaimStage]] = {
    ClaimStage.RAW: frozenset({ClaimStage.NORMALIZED, ClaimStage.QUARANTINED}),
    ClaimStage.NORMALIZED: frozenset({ClaimStage.CLAIMED, ClaimStage.QUARANTINED}),
    ClaimStage.CLAIMED: frozenset({ClaimStage.VERIFIED, ClaimStage.CONTESTED, ClaimStage.QUARANTINED}),
    ClaimStage.VERIFIED: frozenset({ClaimStage.CANDIDATE, ClaimStage.CONTESTED, ClaimStage.REVOKED}),
    ClaimStage.CONTESTED: frozenset({ClaimStage.VERIFIED, ClaimStage.QUARANTINED, ClaimStage.REVOKED}),
    ClaimStage.CANDIDATE: frozenset({ClaimStage.PROMOTED, ClaimStage.QUARANTINED, ClaimStage.REVOKED}),
    ClaimStage.PROMOTED: frozenset({ClaimStage.CONTESTED, ClaimStage.REVOKED}),
    ClaimStage.QUARANTINED: frozenset({ClaimStage.CLAIMED, ClaimStage.REVOKED}),
    ClaimStage.REVOKED: frozenset(),
}


def _unit(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be finite and between 0 and 1")
    return number


def _positive(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and > 0")
    return number


def _digest(*parts: object) -> str:
    raw = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _signed_unit(seed: str) -> float:
    integer = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16)
    return (integer / float(0xFFFFFFFFFFFFFFFF)) * 2.0 - 1.0


@dataclass(frozen=True, slots=True)
class InvariantEnvelope:
    """Hard constraints that evolution is never allowed to mutate."""

    minimum_verification_rate: float = 0.72
    minimum_provenance_completeness: float = 0.98
    minimum_poison_rejection_rate: float = 0.95
    minimum_contradiction_catch_rate: float = 0.85
    maximum_serving_regression: float = 0.0
    require_rollback_ref: bool = True
    serving_writes_forbidden: bool = True

    def __post_init__(self) -> None:
        for name in (
            "minimum_verification_rate",
            "minimum_provenance_completeness",
            "minimum_poison_rejection_rate",
            "minimum_contradiction_catch_rate",
            "maximum_serving_regression",
        ):
            _unit(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class AbsorbSignal:
    event_id: str
    source_id: str
    content_sha256: str
    novelty: float
    utility: float
    staleness: float = 0.0
    uncertainty: float = 0.0
    contradiction_risk: float = 0.0
    poisoning_risk: float = 0.0
    retrieval_gap: float = 0.0
    estimated_cost: float = 1.0
    modality: str = "text"
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.source_id.strip():
            raise ValueError("event_id and source_id are required")
        if len(self.content_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.content_sha256.lower()):
            raise ValueError("content_sha256 must be a sha256 hex digest")
        for name in (
            "novelty", "utility", "staleness", "uncertainty",
            "contradiction_risk", "poisoning_risk", "retrieval_gap",
        ):
            _unit(getattr(self, name), name)
        _positive(self.estimated_cost, "estimated_cost")


@dataclass(frozen=True, slots=True)
class EvolutionContext:
    drift: float = 0.0
    stagnation: float = 0.0
    backlog_pressure: float = 0.0
    regression_risk: float = 0.0
    epistemic_uncertainty: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "drift", "stagnation", "backlog_pressure",
            "regression_risk", "epistemic_uncertainty",
        ):
            _unit(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class AbsorbGenome:
    """Evolvable policy parameters.  Hard safety invariants are intentionally absent."""

    novelty_weight: float = 1.20
    utility_weight: float = 1.35
    staleness_weight: float = 0.75
    uncertainty_weight: float = 0.55
    contradiction_weight: float = 1.10
    poisoning_weight: float = 1.30
    gap_weight: float = 1.15
    cost_weight: float = 0.60
    verification_floor: float = 0.78
    shadow_fraction: float = 0.18
    adversarial_mirror_threshold: float = 0.42
    deep_threshold: float = 0.58
    speculative_threshold: float = 0.68
    refresh_threshold: float = 0.62
    gap_threshold: float = 0.52
    mutation_scale: float = 0.08
    max_parallelism: int = 16

    def __post_init__(self) -> None:
        for name in (
            "novelty_weight", "utility_weight", "staleness_weight",
            "uncertainty_weight", "contradiction_weight", "poisoning_weight",
            "gap_weight", "cost_weight",
        ):
            _positive(getattr(self, name), name)
        for name in (
            "verification_floor", "shadow_fraction", "adversarial_mirror_threshold",
            "deep_threshold", "speculative_threshold", "refresh_threshold",
            "gap_threshold", "mutation_scale",
        ):
            _unit(getattr(self, name), name)
        if self.max_parallelism < 1 or self.max_parallelism > 4096:
            raise ValueError("max_parallelism must be between 1 and 4096")


@dataclass(frozen=True, slots=True)
class Generation:
    generation_id: str
    genome: AbsorbGenome
    role: GenerationRole
    parent_ids: tuple[str, ...] = ()
    sequence: int = 0

    def __post_init__(self) -> None:
        if not self.generation_id.strip():
            raise ValueError("generation_id is required")
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")


@dataclass(frozen=True, slots=True)
class LaneRoute:
    event_id: str
    generation_id: str
    primary: AbsorbLane
    mirrors: tuple[AbsorbLane, ...]
    priority: float
    lane_scores: Mapping[AbsorbLane, float]
    rationale: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GenerationMetrics:
    """Observed shadow/champion performance for one immutable generation."""

    verified_information_gain: float
    retrieval_lift: float
    verification_rate: float
    provenance_completeness: float
    contradiction_catch_rate: float
    poison_rejection_rate: float
    duplicate_suppression: float
    freshness_score: float
    calibration_score: float
    cost_efficiency: float
    latency_efficiency: float
    serving_regression: float = 0.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _unit(getattr(self, name), name)

    def as_policy_metrics(self) -> dict[str, float]:
        return {
            "verified_information_gain": self.verified_information_gain,
            "retrieval_lift": self.retrieval_lift,
            "verification_rate": self.verification_rate,
            "provenance_completeness": self.provenance_completeness,
            "contradiction_catch_rate": self.contradiction_catch_rate,
            "poison_rejection_rate": self.poison_rejection_rate,
            "duplicate_suppression": self.duplicate_suppression,
            "freshness_score": self.freshness_score,
            "calibration_score": self.calibration_score,
            "cost_efficiency": self.cost_efficiency,
            "latency_efficiency": self.latency_efficiency,
            "serving_regression": self.serving_regression,
        }


@dataclass(frozen=True, slots=True)
class GenerationReport:
    generation: Generation
    metrics: GenerationMetrics
    evidence_ids: tuple[str, ...]
    rollback_ref: str
    sample_count: int

    def __post_init__(self) -> None:
        if self.sample_count < 1:
            raise ValueError("sample_count must be >= 1")


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    accepted: bool
    champion_id: str
    candidate_id: str | None
    pareto_frontier: tuple[str, ...]
    gain: float
    violations: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimLifecycle:
    claim_id: str
    stage: ClaimStage = ClaimStage.RAW
    attestation_ids: tuple[str, ...] = ()

    def transition(self, target: ClaimStage, *, attestation_id: str = "") -> "ClaimLifecycle":
        target = ClaimStage(target)
        if target not in _TRANSITIONS[self.stage]:
            raise ValueError(f"illegal claim transition: {self.stage.value} -> {target.value}")
        attestations = self.attestation_ids
        if attestation_id.strip():
            attestations = tuple(dict.fromkeys((*attestations, attestation_id.strip())))
        if target in {ClaimStage.VERIFIED, ClaimStage.CANDIDATE, ClaimStage.PROMOTED} and not attestations:
            raise ValueError(f"{target.value} requires an attestation")
        return replace(self, stage=target, attestation_ids=attestations)


class EvolutionRateController:
    """Raises exploration during drift/stagnation/backlog and damps it under risk."""

    def __init__(self, *, base_rate: float = 0.22, minimum: float = 0.04, maximum: float = 0.92) -> None:
        self.base_rate = _unit(base_rate, "base_rate")
        self.minimum = _unit(minimum, "minimum")
        self.maximum = _unit(maximum, "maximum")
        if minimum > maximum:
            raise ValueError("minimum cannot exceed maximum")

    def rate(self, context: EvolutionContext) -> float:
        pressure = 1.0 + 1.25 * context.drift + 1.10 * context.stagnation + 0.85 * context.backlog_pressure
        damping = 1.0 + 1.65 * context.regression_risk + 0.75 * context.epistemic_uncertainty
        raw = self.base_rate * pressure / damping
        return max(self.minimum, min(self.maximum, raw))

    def challenger_count(self, context: EvolutionContext, *, maximum: int = 12) -> int:
        maximum = max(1, int(maximum))
        return max(1, min(maximum, 1 + math.ceil(self.rate(context) * (maximum - 1))))


class AdaptiveAbsorptionFabric:
    """Policy brain for a generational, shadow-tested absorption plane."""

    def __init__(
        self,
        champion: Generation | None = None,
        *,
        invariants: InvariantEnvelope | None = None,
        rate_controller: EvolutionRateController | None = None,
    ) -> None:
        self.invariants = invariants or InvariantEnvelope()
        self.rate_controller = rate_controller or EvolutionRateController()
        self.champion = champion or Generation("absorb-g0", AbsorbGenome(), GenerationRole.CHAMPION, sequence=0)
        if self.champion.role is not GenerationRole.CHAMPION:
            raise ValueError("champion generation must have CHAMPION role")
        if self.champion.genome.verification_floor < self.invariants.minimum_verification_rate:
            raise ValueError("champion verification floor is below invariant minimum")
        self._policy = self._build_policy()

    def _build_policy(self) -> EvolutionPolicy:
        inv = self.invariants
        return EvolutionPolicy(
            (
                MetricSpec("verified_information_gain", Direction.HIGHER, weight=4.0, max_regression_fraction=0.01),
                MetricSpec("retrieval_lift", Direction.HIGHER, weight=2.4, max_regression_fraction=0.03),
                MetricSpec("verification_rate", Direction.HIGHER, weight=4.0, max_regression_fraction=0.0,
                           floor=inv.minimum_verification_rate),
                MetricSpec("provenance_completeness", Direction.HIGHER, weight=4.0, max_regression_fraction=0.0,
                           floor=inv.minimum_provenance_completeness),
                MetricSpec("contradiction_catch_rate", Direction.HIGHER, weight=3.0, max_regression_fraction=0.0,
                           floor=inv.minimum_contradiction_catch_rate),
                MetricSpec("poison_rejection_rate", Direction.HIGHER, weight=3.5, max_regression_fraction=0.0,
                           floor=inv.minimum_poison_rejection_rate),
                MetricSpec("duplicate_suppression", Direction.HIGHER, weight=1.2, max_regression_fraction=0.08),
                MetricSpec("freshness_score", Direction.HIGHER, weight=1.2, max_regression_fraction=0.08),
                MetricSpec("calibration_score", Direction.HIGHER, weight=2.0, max_regression_fraction=0.03),
                MetricSpec("cost_efficiency", Direction.HIGHER, weight=1.4, max_regression_fraction=0.10),
                MetricSpec("latency_efficiency", Direction.HIGHER, weight=1.0, max_regression_fraction=0.10),
                MetricSpec("serving_regression", Direction.LOWER, weight=5.0, max_regression_fraction=0.0,
                           floor=0.0, ceiling=inv.maximum_serving_regression),
            ),
            minimum_evidence=3,
            evolve_minimum_gain=0.003,
            mutation_minimum_gain=0.02,
        )

    @staticmethod
    def _priority(signal: AbsorbSignal, genome: AbsorbGenome) -> float:
        benefit = (
            genome.novelty_weight * signal.novelty
            + genome.utility_weight * signal.utility
            + genome.staleness_weight * signal.staleness
            + genome.uncertainty_weight * signal.uncertainty
            + genome.contradiction_weight * signal.contradiction_risk
            + genome.poisoning_weight * signal.poisoning_risk
            + genome.gap_weight * signal.retrieval_gap
        )
        penalty = max(0.05, genome.cost_weight * signal.estimated_cost)
        return benefit / penalty

    @staticmethod
    def _lane_scores(signal: AbsorbSignal) -> dict[AbsorbLane, float]:
        return {
            AbsorbLane.FAST: 0.46 * signal.utility + 0.38 * signal.novelty + 0.16 * (1.0 - signal.uncertainty),
            AbsorbLane.DEEP: 0.34 * signal.utility + 0.38 * signal.uncertainty + 0.28 * signal.novelty,
            AbsorbLane.ADVERSARIAL: 0.48 * signal.contradiction_risk + 0.52 * signal.poisoning_risk,
            AbsorbLane.SPECULATIVE: 0.54 * signal.uncertainty + 0.30 * signal.novelty + 0.16 * (1.0 - signal.utility),
            AbsorbLane.REFRESH: 0.70 * signal.staleness + 0.30 * signal.utility,
            AbsorbLane.GAP: 0.72 * signal.retrieval_gap + 0.18 * signal.utility + 0.10 * signal.uncertainty,
        }

    def route(self, signal: AbsorbSignal, generation: Generation | None = None) -> LaneRoute:
        generation = generation or self.champion
        genome = generation.genome
        scores = self._lane_scores(signal)
        eligible: list[AbsorbLane] = [AbsorbLane.FAST]
        if scores[AbsorbLane.DEEP] >= genome.deep_threshold: eligible.append(AbsorbLane.DEEP)
        if scores[AbsorbLane.SPECULATIVE] >= genome.speculative_threshold: eligible.append(AbsorbLane.SPECULATIVE)
        if scores[AbsorbLane.REFRESH] >= genome.refresh_threshold: eligible.append(AbsorbLane.REFRESH)
        if scores[AbsorbLane.GAP] >= genome.gap_threshold: eligible.append(AbsorbLane.GAP)
        if scores[AbsorbLane.ADVERSARIAL] >= genome.adversarial_mirror_threshold: eligible.append(AbsorbLane.ADVERSARIAL)
        primary = max(eligible, key=lambda lane: (scores[lane], lane.value))

        mirrors: list[AbsorbLane] = []
        rationale = [f"primary={primary.value}"]
        risk = max(signal.contradiction_risk, signal.poisoning_risk)
        if risk >= genome.adversarial_mirror_threshold and primary is not AbsorbLane.ADVERSARIAL:
            mirrors.append(AbsorbLane.ADVERSARIAL); rationale.append("risk-forced-adversarial-mirror")
        if signal.uncertainty >= genome.deep_threshold and primary is not AbsorbLane.DEEP:
            mirrors.append(AbsorbLane.DEEP); rationale.append("uncertainty-deep-mirror")
        if signal.retrieval_gap >= genome.gap_threshold and primary is not AbsorbLane.GAP:
            mirrors.append(AbsorbLane.GAP); rationale.append("retrieval-gap-mirror")
        mirrors = list(dict.fromkeys(mirrors))
        return LaneRoute(
            event_id=signal.event_id,
            generation_id=generation.generation_id,
            primary=primary,
            mirrors=tuple(mirrors),
            priority=self._priority(signal, genome),
            lane_scores=scores,
            rationale=tuple(rationale),
        )

    def shadow_generations(self, signal: AbsorbSignal, challengers: Sequence[Generation]) -> tuple[Generation, ...]:
        """Deterministically mirror only the configured fraction of events to each challenger."""
        selected: list[Generation] = []
        for challenger in challengers:
            if challenger.role is not GenerationRole.CHALLENGER:
                continue
            bucket = int(_digest(signal.event_id, challenger.generation_id)[:8], 16) / 0xFFFFFFFF
            if bucket < challenger.genome.shadow_fraction:
                selected.append(challenger)
        return tuple(selected)

    def spawn_challengers(
        self,
        context: EvolutionContext,
        *,
        maximum: int = 12,
        sequence_start: int | None = None,
    ) -> tuple[Generation, ...]:
        count = self.rate_controller.challenger_count(context, maximum=maximum)
        rate = self.rate_controller.rate(context)
        start = self.champion.sequence + 1 if sequence_start is None else max(0, int(sequence_start))
        return tuple(self._mutate(self.champion, rate=rate, ordinal=i, sequence=start + i) for i in range(count))

    def _mutate(self, parent: Generation, *, rate: float, ordinal: int, sequence: int) -> Generation:
        scale = min(0.35, max(0.01, parent.genome.mutation_scale * (0.55 + 1.8 * rate)))
        fields = parent.genome.__dataclass_fields__
        values: dict[str, object] = {}
        for name in fields:
            current = getattr(parent.genome, name)
            if name == "max_parallelism":
                delta = round(_signed_unit(f"{parent.generation_id}:{ordinal}:{name}") * max(1, 12 * rate))
                values[name] = max(1, min(4096, int(current) + delta))
                continue
            perturb = _signed_unit(f"{parent.generation_id}:{ordinal}:{name}") * scale
            if name.endswith("_weight"):
                values[name] = max(0.05, float(current) * (1.0 + perturb))
            else:
                values[name] = max(0.01, min(0.99, float(current) + perturb))
        values["verification_floor"] = max(
            float(values["verification_floor"]), self.invariants.minimum_verification_rate
        )
        genome = AbsorbGenome(**values)
        gid = f"absorb-g{sequence}-{_digest(parent.generation_id, ordinal, sequence, round(rate, 6))[:10]}"
        return Generation(gid, genome, GenerationRole.CHALLENGER, (parent.generation_id,), sequence)

    @staticmethod
    def crossover(left: Generation, right: Generation, *, sequence: int) -> Generation:
        """Deterministically combine two safe genomes; caller still must evaluate it in shadow."""
        if left.role is GenerationRole.ARCHIVED or right.role is GenerationRole.ARCHIVED:
            raise ValueError("cannot crossover archived generations")
        values: dict[str, object] = {}
        for index, name in enumerate(left.genome.__dataclass_fields__):
            a, b = getattr(left.genome, name), getattr(right.genome, name)
            if name == "max_parallelism":
                values[name] = max(1, round((int(a) + int(b)) / 2))
            elif index % 3 == 0:
                values[name] = (float(a) + float(b)) / 2.0
            else:
                values[name] = a if int(_digest(left.generation_id, right.generation_id, name)[:2], 16) % 2 == 0 else b
        genome = AbsorbGenome(**values)
        gid = f"absorb-g{sequence}-x-{_digest(left.generation_id, right.generation_id, sequence)[:10]}"
        return Generation(gid, genome, GenerationRole.CHALLENGER, (left.generation_id, right.generation_id), sequence)

    def _invariant_violations(self, report: GenerationReport) -> tuple[str, ...]:
        metrics = report.metrics
        violations: list[str] = []
        inv = self.invariants
        if report.generation.role is not GenerationRole.CHALLENGER:
            violations.append("only challengers may be promoted")
        if report.generation.genome.verification_floor < inv.minimum_verification_rate:
            violations.append("genome verification floor below invariant")
        if metrics.verification_rate < inv.minimum_verification_rate:
            violations.append("verification rate below invariant")
        if metrics.provenance_completeness < inv.minimum_provenance_completeness:
            violations.append("provenance completeness below invariant")
        if metrics.poison_rejection_rate < inv.minimum_poison_rejection_rate:
            violations.append("poison rejection below invariant")
        if metrics.contradiction_catch_rate < inv.minimum_contradiction_catch_rate:
            violations.append("contradiction catch below invariant")
        if metrics.serving_regression > inv.maximum_serving_regression:
            violations.append("serving regression exceeds invariant")
        if inv.require_rollback_ref and not report.rollback_ref.strip():
            violations.append("rollback reference required")
        if report.sample_count < 100:
            violations.append("shadow sample count below 100")
        return tuple(violations)

    @staticmethod
    def _pareto_values(metrics: GenerationMetrics) -> tuple[float, ...]:
        return (
            metrics.verified_information_gain, metrics.retrieval_lift,
            metrics.verification_rate, metrics.provenance_completeness,
            metrics.contradiction_catch_rate, metrics.poison_rejection_rate,
            metrics.duplicate_suppression, metrics.freshness_score,
            metrics.calibration_score, metrics.cost_efficiency, metrics.latency_efficiency,
            1.0 - metrics.serving_regression,
        )

    @classmethod
    def _dominates(cls, left: GenerationMetrics, right: GenerationMetrics) -> bool:
        a, b = cls._pareto_values(left), cls._pareto_values(right)
        return all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b))

    def select_promotion(
        self,
        champion_metrics: GenerationMetrics,
        reports: Iterable[GenerationReport],
    ) -> PromotionDecision:
        valid: list[GenerationReport] = []
        rejected: dict[str, tuple[str, ...]] = {}
        for report in reports:
            violations = self._invariant_violations(report)
            if violations:
                rejected[report.generation.generation_id] = violations
            else:
                valid.append(report)
        if not valid:
            flat = tuple(f"{gid}: {reason}" for gid, rows in rejected.items() for reason in rows)
            return PromotionDecision(False, self.champion.generation_id, None, (), 0.0, flat,
                                     ("no challenger satisfied the non-evolvable envelope",))

        frontier = [
            report for report in valid
            if not any(self._dominates(other.metrics, report.metrics) for other in valid if other is not report)
        ]
        scored: list[tuple[float, GenerationReport, tuple[str, ...], tuple[str, ...]]] = []
        baseline = champion_metrics.as_policy_metrics()
        for report in frontier:
            candidate = EvolutionCandidate(
                candidate_id=report.generation.generation_id,
                baseline_id=self.champion.generation_id,
                metrics=report.metrics.as_policy_metrics(),
                evidence_ids=report.evidence_ids,
                rollback_ref=report.rollback_ref,
                scope=("absorption-plane",),
            )
            decision = self._policy.evaluate(baseline, candidate)
            if decision.accepted:
                scored.append((decision.gain, report, decision.violations, decision.reasons))
        frontier_ids = tuple(sorted(x.generation.generation_id for x in frontier))
        if not scored:
            return PromotionDecision(False, self.champion.generation_id, None, frontier_ids, 0.0, (),
                                     ("safe Pareto challengers did not beat the measured adoption threshold",))
        scored.sort(key=lambda row: (row[0], row[1].metrics.verified_information_gain,
                                     row[1].sample_count, row[1].generation.generation_id), reverse=True)
        gain, winner, violations, reasons = scored[0]
        return PromotionDecision(True, self.champion.generation_id, winner.generation.generation_id,
                                 frontier_ids, gain, violations, reasons)

    def promote(self, report: GenerationReport, champion_metrics: GenerationMetrics) -> "AdaptiveAbsorptionFabric":
        decision = self.select_promotion(champion_metrics, (report,))
        if not decision.accepted:
            raise ValueError("challenger did not pass promotion gate")
        promoted = replace(report.generation, role=GenerationRole.CHAMPION)
        return AdaptiveAbsorptionFabric(promoted, invariants=self.invariants, rate_controller=self.rate_controller)


def serving_feedback_to_signal(
    *,
    event_id: str,
    source_id: str,
    content_sha256: str,
    retrieval_miss: float = 0.0,
    uncertainty: float = 0.0,
    stale_hit: float = 0.0,
    user_correction: float = 0.0,
) -> AbsorbSignal:
    """Convert one-way serving telemetry into a GAP/REFRESH candidate.

    This returns an absorption event; it never mutates serving memory.  The durable
    outbox is expected to carry the returned event across the serving boundary.
    """
    miss = _unit(retrieval_miss, "retrieval_miss")
    uncertainty = _unit(uncertainty, "uncertainty")
    stale = _unit(stale_hit, "stale_hit")
    correction = _unit(user_correction, "user_correction")
    return AbsorbSignal(
        event_id=event_id,
        source_id=source_id,
        content_sha256=content_sha256,
        novelty=max(miss, correction) * 0.8,
        utility=max(miss, correction, stale),
        staleness=stale,
        uncertainty=max(uncertainty, correction),
        contradiction_risk=correction,
        poisoning_risk=0.0,
        retrieval_gap=max(miss, correction),
        estimated_cost=1.0,
        modality="serving-feedback",
        tags=("orthogonal-feedback",),
    )
