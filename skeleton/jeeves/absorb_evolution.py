"""High-rate generational evolution for the Jeeves absorb plane.

The base absorb engine owns truth promotion and immutable snapshots.  This module
owns *policy evolution* around that engine.  It deliberately evolves only
scheduling/routing policy: the PromotionGate is fingerprinted and treated as a
non-evolvable constitution.

A champion serves production absorption.  Deterministically sampled observations
are mirrored to shadow challengers, which may mutate routing thresholds and
resource posture.  Challengers are selected through hard invariant checks, a
Pareto frontier, and measured gain.  Promotion swaps only ``engine.router``;
challengers never publish snapshots.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, fields
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .absorb import (
    AbsorbEngine,
    AbsorbError,
    AbsorbLane,
    AbsorbSignals,
    AdaptiveRouter,
    GateConfig,
    RouterConfig,
    Verification,
)


_EPS = 1e-9


def _unit(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AbsorbError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise AbsorbError(f"{name} must be finite and between 0 and 1")
    return number


def _positive(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AbsorbError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise AbsorbError(f"{name} must be finite and positive")
    return number


def _hash(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(map(str, parts)).encode("utf-8")).hexdigest()


def _signed(seed: str) -> float:
    value = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16)
    return (value / float(0xFFFFFFFFFFFFFFFF)) * 2.0 - 1.0


def gate_fingerprint(config: GateConfig) -> str:
    payload = tuple((field.name, getattr(config, field.name)) for field in fields(config))
    return _hash("gate-v1", *payload)


class GenerationRole(str, Enum):
    CHAMPION = "champion"
    CHALLENGER = "challenger"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class EvolutionContext:
    drift: float = 0.0
    stagnation: float = 0.0
    backlog_pressure: float = 0.0
    serving_pressure: float = 0.0
    regression_risk: float = 0.0
    epistemic_uncertainty: float = 0.0

    def __post_init__(self) -> None:
        for field in fields(self):
            object.__setattr__(self, field.name, _unit(field.name, getattr(self, field.name)))


@dataclass(frozen=True, slots=True)
class RouterGenome:
    """Mutable policy surface.  Promotion thresholds are intentionally excluded."""

    deep_threshold: float = 0.32
    challenge_threshold: float = 0.55
    uncertainty_threshold: float = 0.30
    high_impact_threshold: float = 0.75
    shadow_fraction: float = 0.18
    mutation_scale: float = 0.08
    challenge_reserve: float = 0.18
    deep_reserve: float = 0.28
    champion_compute_fraction: float = 0.64

    def __post_init__(self) -> None:
        for field in fields(self):
            object.__setattr__(self, field.name, _unit(field.name, getattr(self, field.name)))
        if self.challenge_reserve + self.deep_reserve > 0.85:
            raise AbsorbError("protected lane reserves exceed 85%")
        if self.champion_compute_fraction < 0.35:
            raise AbsorbError("champion_compute_fraction must be >= 0.35")

    def router_config(self) -> RouterConfig:
        return RouterConfig(
            deep_threshold=self.deep_threshold,
            challenge_threshold=self.challenge_threshold,
            uncertainty_threshold=self.uncertainty_threshold,
            high_impact_threshold=self.high_impact_threshold,
        )


@dataclass(frozen=True, slots=True)
class PolicyGeneration:
    generation_id: str
    genome: RouterGenome
    role: GenerationRole
    sequence: int
    parent_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.generation_id.strip():
            raise AbsorbError("generation_id is required")
        if self.sequence < 0:
            raise AbsorbError("generation sequence must be non-negative")

    def router(self) -> AdaptiveRouter:
        return AdaptiveRouter(self.genome.router_config())


@dataclass(frozen=True, slots=True)
class ShadowRoute:
    generation_id: str
    lanes: tuple[AbsorbLane, ...]
    mirrored: bool


@dataclass(frozen=True, slots=True)
class EvolutionMetrics:
    """Comparable shadow metrics, all normalized so higher is better except impact."""

    verified_information_gain: float
    knowledge_gain_per_compute: float
    promotion_precision: float
    challenge_catch_rate: float
    contradiction_rejection: float
    duplicate_suppression: float
    freshness: float
    calibration: float
    throughput_efficiency: float
    serving_impact: float = 0.0

    def __post_init__(self) -> None:
        for field in fields(self):
            object.__setattr__(self, field.name, _unit(field.name, getattr(self, field.name)))

    def vector(self) -> tuple[float, ...]:
        return (
            self.verified_information_gain,
            self.knowledge_gain_per_compute,
            self.promotion_precision,
            self.challenge_catch_rate,
            self.contradiction_rejection,
            self.duplicate_suppression,
            self.freshness,
            self.calibration,
            self.throughput_efficiency,
            1.0 - self.serving_impact,
        )


@dataclass(frozen=True, slots=True)
class GenerationEvaluation:
    generation: PolicyGeneration
    metrics: EvolutionMetrics
    sample_count: int
    evidence_ids: tuple[str, ...]
    rollback_snapshot: int | None
    gate_fingerprint: str

    def __post_init__(self) -> None:
        if self.sample_count < 1:
            raise AbsorbError("sample_count must be positive")


@dataclass(frozen=True, slots=True)
class EvolutionEnvelope:
    """Non-evolvable acceptance floors for policy generations."""

    min_promotion_precision: float = 0.95
    min_challenge_catch_rate: float = 0.85
    min_contradiction_rejection: float = 0.90
    max_serving_impact: float = 0.0
    minimum_shadow_samples: int = 256
    minimum_evidence: int = 3

    def __post_init__(self) -> None:
        for name in (
            "min_promotion_precision",
            "min_challenge_catch_rate",
            "min_contradiction_rejection",
            "max_serving_impact",
        ):
            object.__setattr__(self, name, _unit(name, getattr(self, name)))
        if self.minimum_shadow_samples < 1 or self.minimum_evidence < 1:
            raise AbsorbError("minimum sample/evidence counts must be positive")


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    accepted: bool
    champion_id: str
    candidate_id: str | None
    gain: float
    pareto_frontier: tuple[str, ...]
    violations: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    champion: float
    challengers: float
    challenge_lane: float
    deep_lane: float

    def __post_init__(self) -> None:
        for field in fields(self):
            object.__setattr__(self, field.name, _unit(field.name, getattr(self, field.name)))
        if self.champion + self.challengers > 1.0 + _EPS:
            raise AbsorbError("champion + challenger budget cannot exceed 1")


class EvolutionRateController:
    """Fast evolutionary clock with risk-aware damping."""

    def __init__(
        self,
        *,
        base_rate: float = 0.34,
        minimum_rate: float = 0.06,
        maximum_rate: float = 0.95,
        max_challengers: int = 16,
    ) -> None:
        self.base_rate = _unit("base_rate", base_rate)
        self.minimum_rate = _unit("minimum_rate", minimum_rate)
        self.maximum_rate = _unit("maximum_rate", maximum_rate)
        if self.minimum_rate > self.maximum_rate:
            raise AbsorbError("minimum_rate cannot exceed maximum_rate")
        if max_challengers < 1 or max_challengers > 128:
            raise AbsorbError("max_challengers must be between 1 and 128")
        self.max_challengers = max_challengers

    def rate(self, context: EvolutionContext) -> float:
        accelerator = (
            1.0
            + 1.35 * context.drift
            + 1.15 * context.stagnation
            + 0.90 * context.backlog_pressure
        )
        damping = (
            1.0
            + 1.80 * context.regression_risk
            + 0.85 * context.epistemic_uncertainty
            + 1.20 * context.serving_pressure
        )
        raw = self.base_rate * accelerator / damping
        return max(self.minimum_rate, min(self.maximum_rate, raw))

    def challenger_count(self, context: EvolutionContext) -> int:
        rate = self.rate(context)
        return max(1, min(self.max_challengers, 1 + math.ceil(rate * (self.max_challengers - 1))))

    def budget(self, context: EvolutionContext, genome: RouterGenome) -> ResourceBudget:
        rate = self.rate(context)
        headroom = max(0.0, 1.0 - context.serving_pressure)
        challenger = min(0.45, rate * 0.42 * headroom)
        champion = min(genome.champion_compute_fraction, 1.0 - challenger)
        return ResourceBudget(
            champion=champion,
            challengers=challenger,
            challenge_lane=genome.challenge_reserve,
            deep_lane=genome.deep_reserve,
        )


class AbsorbEvolutionArena:
    """Shadow population manager for a live ``AbsorbEngine``."""

    def __init__(
        self,
        engine: AbsorbEngine,
        *,
        champion: PolicyGeneration | None = None,
        envelope: EvolutionEnvelope | None = None,
        rate_controller: EvolutionRateController | None = None,
    ) -> None:
        self.engine = engine
        self.envelope = envelope or EvolutionEnvelope()
        self.rate_controller = rate_controller or EvolutionRateController()
        self._gate_fingerprint = gate_fingerprint(engine.gate.config)
        genome = champion.genome if champion is not None else self._genome_from_router(engine.router)
        self.champion = champion or PolicyGeneration(
            "absorb-policy-g0", genome, GenerationRole.CHAMPION, sequence=0
        )
        if self.champion.role is not GenerationRole.CHAMPION:
            raise AbsorbError("champion must have CHAMPION role")

    @staticmethod
    def _genome_from_router(router: AdaptiveRouter) -> RouterGenome:
        config = router.config
        return RouterGenome(
            deep_threshold=config.deep_threshold,
            challenge_threshold=config.challenge_threshold,
            uncertainty_threshold=config.uncertainty_threshold,
            high_impact_threshold=config.high_impact_threshold,
        )

    def assert_gate_unchanged(self) -> None:
        current = gate_fingerprint(self.engine.gate.config)
        if current != self._gate_fingerprint:
            raise AbsorbError(
                "promotion gate changed during policy evolution",
                context={"expected": self._gate_fingerprint, "current": current},
            )

    def spawn_challengers(self, context: EvolutionContext) -> tuple[PolicyGeneration, ...]:
        self.assert_gate_unchanged()
        count = self.rate_controller.challenger_count(context)
        rate = self.rate_controller.rate(context)
        return tuple(self._mutate(self.champion, rate, ordinal) for ordinal in range(count))

    def _mutate(self, parent: PolicyGeneration, rate: float, ordinal: int) -> PolicyGeneration:
        amplitude = min(0.30, max(0.01, parent.genome.mutation_scale * (0.65 + 1.9 * rate)))
        values: dict[str, float] = {}
        for field in fields(parent.genome):
            name = field.name
            current = float(getattr(parent.genome, name))
            shift = _signed(f"{parent.generation_id}:{ordinal}:{name}") * amplitude
            if name in {"challenge_reserve", "deep_reserve", "champion_compute_fraction"}:
                candidate = current * (1.0 + shift)
            else:
                candidate = current + shift
            values[name] = max(0.01, min(0.99, candidate))
        if values["challenge_reserve"] + values["deep_reserve"] > 0.85:
            scale = 0.85 / (values["challenge_reserve"] + values["deep_reserve"])
            values["challenge_reserve"] *= scale
            values["deep_reserve"] *= scale
        values["champion_compute_fraction"] = max(0.35, values["champion_compute_fraction"])
        genome = RouterGenome(**values)
        sequence = parent.sequence + ordinal + 1
        generation_id = f"absorb-policy-g{sequence}-{_hash(parent.generation_id, ordinal, round(rate, 6))[:10]}"
        return PolicyGeneration(
            generation_id,
            genome,
            GenerationRole.CHALLENGER,
            sequence,
            (parent.generation_id,),
        )

    def crossover(
        self,
        left: PolicyGeneration,
        right: PolicyGeneration,
        *,
        sequence: int,
    ) -> PolicyGeneration:
        if left.role is GenerationRole.ARCHIVED or right.role is GenerationRole.ARCHIVED:
            raise AbsorbError("archived generations cannot reproduce")
        values: dict[str, float] = {}
        for index, field in enumerate(fields(left.genome)):
            name = field.name
            a, b = float(getattr(left.genome, name)), float(getattr(right.genome, name))
            if index % 3 == 0:
                values[name] = (a + b) / 2.0
            else:
                values[name] = a if int(_hash(left.generation_id, right.generation_id, name)[:2], 16) % 2 == 0 else b
        if values["challenge_reserve"] + values["deep_reserve"] > 0.85:
            scale = 0.85 / (values["challenge_reserve"] + values["deep_reserve"])
            values["challenge_reserve"] *= scale
            values["deep_reserve"] *= scale
        values["champion_compute_fraction"] = max(0.35, values["champion_compute_fraction"])
        generation_id = f"absorb-policy-g{sequence}-x-{_hash(left.generation_id, right.generation_id, sequence)[:10]}"
        return PolicyGeneration(
            generation_id,
            RouterGenome(**values),
            GenerationRole.CHALLENGER,
            sequence,
            (left.generation_id, right.generation_id),
        )

    @staticmethod
    def _shadow_bucket(event_key: str, generation_id: str) -> float:
        return int(_hash(event_key, generation_id)[:8], 16) / float(0xFFFFFFFF)

    def shadow_routes(
        self,
        event_key: str,
        signals: AbsorbSignals,
        verification: Verification,
        challengers: Sequence[PolicyGeneration],
    ) -> tuple[ShadowRoute, ...]:
        """Evaluate routing in shadow without executing or promoting challenger work."""
        rows: list[ShadowRoute] = []
        for generation in challengers:
            if generation.role is not GenerationRole.CHALLENGER:
                continue
            mirrored = self._shadow_bucket(event_key, generation.generation_id) < generation.genome.shadow_fraction
            lanes = generation.router().lanes(signals, verification) if mirrored else ()
            rows.append(ShadowRoute(generation.generation_id, lanes, mirrored))
        return tuple(rows)

    def _violations(self, evaluation: GenerationEvaluation) -> tuple[str, ...]:
        metrics = evaluation.metrics
        env = self.envelope
        violations: list[str] = []
        if evaluation.generation.role is not GenerationRole.CHALLENGER:
            violations.append("only shadow challengers may be promoted")
        if evaluation.gate_fingerprint != self._gate_fingerprint:
            violations.append("promotion gate fingerprint mismatch")
        if evaluation.sample_count < env.minimum_shadow_samples:
            violations.append("insufficient shadow samples")
        if len(set(evaluation.evidence_ids)) < env.minimum_evidence:
            violations.append("insufficient independent evaluation evidence")
        if evaluation.rollback_snapshot is None:
            violations.append("rollback snapshot required")
        if metrics.promotion_precision < env.min_promotion_precision:
            violations.append("promotion precision below invariant")
        if metrics.challenge_catch_rate < env.min_challenge_catch_rate:
            violations.append("challenge catch rate below invariant")
        if metrics.contradiction_rejection < env.min_contradiction_rejection:
            violations.append("contradiction rejection below invariant")
        if metrics.serving_impact > env.max_serving_impact:
            violations.append("serving impact exceeds invariant")
        return tuple(violations)

    @staticmethod
    def _dominates(left: EvolutionMetrics, right: EvolutionMetrics) -> bool:
        a, b = left.vector(), right.vector()
        return all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b))

    @staticmethod
    def _gain(baseline: EvolutionMetrics, candidate: EvolutionMetrics) -> float:
        weights = (4.0, 3.0, 4.0, 3.5, 3.5, 1.2, 1.0, 2.0, 1.4, 5.0)
        total = 0.0
        for base, value, weight in zip(baseline.vector(), candidate.vector(), weights):
            fraction = (value - base) / max(abs(base), 0.05)
            total += max(-2.0, min(2.0, fraction)) * weight
        return total / sum(weights)

    def select_promotion(
        self,
        baseline: EvolutionMetrics,
        evaluations: Iterable[GenerationEvaluation],
        *,
        minimum_gain: float = 0.01,
    ) -> PromotionDecision:
        self.assert_gate_unchanged()
        minimum_gain = _unit("minimum_gain", minimum_gain)
        valid: list[GenerationEvaluation] = []
        rejected: dict[str, tuple[str, ...]] = {}
        for evaluation in evaluations:
            violations = self._violations(evaluation)
            if violations:
                rejected[evaluation.generation.generation_id] = violations
            else:
                valid.append(evaluation)
        if not valid:
            reasons = tuple(
                f"{generation_id}: {violation}"
                for generation_id, violations in rejected.items()
                for violation in violations
            )
            return PromotionDecision(
                False, self.champion.generation_id, None, 0.0, (), reasons,
                ("no challenger satisfied the non-evolvable envelope",),
            )
        frontier = [
            row for row in valid
            if not any(self._dominates(other.metrics, row.metrics) for other in valid if other is not row)
        ]
        scored = [(self._gain(baseline, row.metrics), row) for row in frontier]
        scored.sort(
            key=lambda item: (
                item[0],
                item[1].metrics.verified_information_gain,
                item[1].sample_count,
                item[1].generation.generation_id,
            ),
            reverse=True,
        )
        gain, winner = scored[0]
        frontier_ids = tuple(sorted(row.generation.generation_id for row in frontier))
        if gain <= minimum_gain:
            return PromotionDecision(
                False, self.champion.generation_id, None, gain, frontier_ids, (),
                (f"best measured gain {gain:.6f} did not exceed {minimum_gain:.6f}",),
            )
        return PromotionDecision(
            True,
            self.champion.generation_id,
            winner.generation.generation_id,
            gain,
            frontier_ids,
            (),
            ("safe Pareto challenger produced measurable improvement",),
        )

    def promote(
        self,
        baseline: EvolutionMetrics,
        evaluation: GenerationEvaluation,
        *,
        minimum_gain: float = 0.01,
    ) -> PromotionDecision:
        """Install only the winning router; the promotion gate and snapshots are untouched."""
        decision = self.select_promotion(baseline, (evaluation,), minimum_gain=minimum_gain)
        if not decision.accepted:
            return decision
        self.assert_gate_unchanged()
        self.engine.router = evaluation.generation.router()
        self.champion = PolicyGeneration(
            evaluation.generation.generation_id,
            evaluation.generation.genome,
            GenerationRole.CHAMPION,
            evaluation.generation.sequence,
            evaluation.generation.parent_ids,
        )
        self.assert_gate_unchanged()
        return decision

    def status(self, context: EvolutionContext | None = None) -> Mapping[str, object]:
        context = context or EvolutionContext()
        return {
            "champion": self.champion.generation_id,
            "generation_sequence": self.champion.sequence,
            "evolution_rate": self.rate_controller.rate(context),
            "challenger_target": self.rate_controller.challenger_count(context),
            "resource_budget": self.rate_controller.budget(context, self.champion.genome),
            "gate_fingerprint": self._gate_fingerprint,
            "gate_mutable": False,
            "shadow_only_challengers": True,
        }
