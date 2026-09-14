"""Measured evolve-first policy for Jeeves and Galaxy Studio.

The default is evolution: propose a candidate, evaluate it against the current
baseline with explicit metrics and evidence, then adopt only when measured value
improves without violating protected constraints.  Broad mutation is a stronger
operation and therefore requires a rollback reference plus a higher gain bar.

The module is deliberately provider/runtime agnostic.  It evaluates evidence;
it does not generate changes itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class Direction(str, Enum):
    HIGHER = "higher"
    LOWER = "lower"


class ChangeMode(str, Enum):
    EVOLVE = "evolve"
    MUTATE = "mutate"


@dataclass(frozen=True)
class MetricSpec:
    name: str
    direction: Direction = Direction.HIGHER
    weight: float = 1.0
    max_regression_fraction: float = 0.05
    floor: float | None = None
    ceiling: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("metric name must be non-empty")
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("metric weight must be finite and > 0")
        if not math.isfinite(self.max_regression_fraction) or self.max_regression_fraction < 0:
            raise ValueError("max_regression_fraction must be finite and >= 0")
        if self.floor is not None and not math.isfinite(self.floor):
            raise ValueError("metric floor must be finite")
        if self.ceiling is not None and not math.isfinite(self.ceiling):
            raise ValueError("metric ceiling must be finite")
        if self.floor is not None and self.ceiling is not None and self.floor > self.ceiling:
            raise ValueError("metric floor cannot exceed ceiling")


@dataclass(frozen=True)
class EvolutionCandidate:
    candidate_id: str
    baseline_id: str
    metrics: Mapping[str, float]
    evidence_ids: Sequence[str]
    mode: ChangeMode = ChangeMode.EVOLVE
    rollback_ref: str | None = None
    scope: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.baseline_id.strip():
            raise ValueError("candidate_id and baseline_id are required")
        if self.candidate_id == self.baseline_id:
            raise ValueError("candidate and baseline identities must differ")
        for name, value in self.metrics.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("metric names must be non-empty strings")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                raise ValueError(f"metric {name!r} must be a finite number")


@dataclass(frozen=True)
class MetricDelta:
    name: str
    baseline: float
    candidate: float
    directional_fraction: float
    weighted_fraction: float
    regressed: bool
    constraint_ok: bool


@dataclass(frozen=True)
class EvolutionDecision:
    accepted: bool
    candidate_id: str
    baseline_id: str
    mode: ChangeMode
    gain: float
    required_gain: float
    evidence_count: int
    metric_deltas: tuple[MetricDelta, ...]
    violations: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "candidate_id": self.candidate_id,
            "baseline_id": self.baseline_id,
            "mode": self.mode.value,
            "gain": round(self.gain, 8),
            "required_gain": self.required_gain,
            "evidence_count": self.evidence_count,
            "violations": list(self.violations),
            "reasons": list(self.reasons),
            "metrics": [
                {
                    "name": row.name,
                    "baseline": row.baseline,
                    "candidate": row.candidate,
                    "directional_fraction": round(row.directional_fraction, 8),
                    "weighted_fraction": round(row.weighted_fraction, 8),
                    "regressed": row.regressed,
                    "constraint_ok": row.constraint_ok,
                }
                for row in self.metric_deltas
            ],
        }


class EvolutionPolicy:
    """Adopt measurable improvement; fail closed on missing truth or regressions."""

    def __init__(
        self,
        metrics: Sequence[MetricSpec],
        *,
        minimum_evidence: int = 1,
        evolve_minimum_gain: float = 0.0,
        mutation_minimum_gain: float = 0.03,
        epsilon: float = 1e-9,
        improvement_cap: float = 5.0,
    ) -> None:
        if not metrics:
            raise ValueError("at least one metric is required")
        names = [metric.name for metric in metrics]
        if len(set(names)) != len(names):
            raise ValueError("metric names must be unique")
        if minimum_evidence < 1:
            raise ValueError("minimum_evidence must be >= 1")
        if not math.isfinite(evolve_minimum_gain) or not math.isfinite(mutation_minimum_gain):
            raise ValueError("gain thresholds must be finite")
        if mutation_minimum_gain < evolve_minimum_gain:
            raise ValueError("mutation must not have a lower adoption bar than evolution")
        self.metrics = tuple(metrics)
        self.minimum_evidence = int(minimum_evidence)
        self.evolve_minimum_gain = float(evolve_minimum_gain)
        self.mutation_minimum_gain = float(mutation_minimum_gain)
        self.epsilon = max(float(epsilon), 1e-15)
        self.improvement_cap = max(float(improvement_cap), self.epsilon)

    def _fraction(self, spec: MetricSpec, baseline: float, candidate: float) -> float:
        scale = max(abs(baseline), self.epsilon)
        raw = (candidate - baseline) / scale
        if spec.direction is Direction.LOWER:
            raw = -raw
        return max(-self.improvement_cap, min(self.improvement_cap, raw))

    @staticmethod
    def _constraint_ok(spec: MetricSpec, candidate: float) -> bool:
        if spec.floor is not None and candidate < spec.floor:
            return False
        if spec.ceiling is not None and candidate > spec.ceiling:
            return False
        return True

    def evaluate(
        self,
        baseline_metrics: Mapping[str, float],
        candidate: EvolutionCandidate,
    ) -> EvolutionDecision:
        violations: list[str] = []
        reasons: list[str] = []
        rows: list[MetricDelta] = []
        weighted_sum = 0.0
        total_weight = 0.0

        evidence = tuple(dict.fromkeys(str(e).strip() for e in candidate.evidence_ids if str(e).strip()))
        if len(evidence) < self.minimum_evidence:
            violations.append(
                f"insufficient evidence: {len(evidence)} < {self.minimum_evidence}"
            )
        if candidate.mode is ChangeMode.MUTATE and not (candidate.rollback_ref or "").strip():
            violations.append("mutation requires rollback_ref")

        for spec in self.metrics:
            if spec.name not in baseline_metrics:
                violations.append(f"baseline missing metric: {spec.name}")
                continue
            if spec.name not in candidate.metrics:
                violations.append(f"candidate missing metric: {spec.name}")
                continue
            base = float(baseline_metrics[spec.name])
            value = float(candidate.metrics[spec.name])
            if not math.isfinite(base) or not math.isfinite(value):
                violations.append(f"non-finite metric: {spec.name}")
                continue

            fraction = self._fraction(spec, base, value)
            constraint_ok = self._constraint_ok(spec, value)
            regressed = fraction < 0
            if not constraint_ok:
                violations.append(f"hard constraint violated: {spec.name}")
            if fraction < -spec.max_regression_fraction:
                violations.append(
                    f"regression exceeds tolerance: {spec.name} "
                    f"({fraction:.4f} < {-spec.max_regression_fraction:.4f})"
                )
            weighted = fraction * spec.weight
            weighted_sum += weighted
            total_weight += spec.weight
            rows.append(
                MetricDelta(
                    name=spec.name,
                    baseline=base,
                    candidate=value,
                    directional_fraction=fraction,
                    weighted_fraction=weighted,
                    regressed=regressed,
                    constraint_ok=constraint_ok,
                )
            )

        gain = weighted_sum / total_weight if total_weight else float("-inf")
        required_gain = (
            self.mutation_minimum_gain
            if candidate.mode is ChangeMode.MUTATE
            else self.evolve_minimum_gain
        )
        if not math.isfinite(gain):
            violations.append("candidate is not scoreable")
        elif gain <= required_gain:
            reasons.append(
                f"measured gain {gain:.6f} does not exceed adoption threshold {required_gain:.6f}"
            )

        accepted = not violations and math.isfinite(gain) and gain > required_gain
        if accepted:
            reasons.append(
                "candidate improves the weighted baseline within protected tolerances"
            )
            if candidate.mode is ChangeMode.MUTATE:
                reasons.append("mutation passed the stricter gain and rollback requirements")
        elif violations:
            reasons.append("fail-closed: protected evolution constraints were not satisfied")

        return EvolutionDecision(
            accepted=accepted,
            candidate_id=candidate.candidate_id,
            baseline_id=candidate.baseline_id,
            mode=candidate.mode,
            gain=gain,
            required_gain=required_gain,
            evidence_count=len(evidence),
            metric_deltas=tuple(rows),
            violations=tuple(violations),
            reasons=tuple(reasons),
        )


def default_jeeves_policy() -> EvolutionPolicy:
    """Conservative defaults for shared game/AI runtime evolution."""
    return EvolutionPolicy(
        (
            MetricSpec("quality", Direction.HIGHER, weight=4.0, max_regression_fraction=0.01, floor=0.0),
            MetricSpec("reliability", Direction.HIGHER, weight=4.0, max_regression_fraction=0.0, floor=0.0),
            MetricSpec("latency_ms", Direction.LOWER, weight=1.5, max_regression_fraction=0.10, floor=0.0),
            MetricSpec("cost", Direction.LOWER, weight=1.0, max_regression_fraction=0.15, floor=0.0),
        ),
        minimum_evidence=2,
        evolve_minimum_gain=0.002,
        mutation_minimum_gain=0.03,
    )
