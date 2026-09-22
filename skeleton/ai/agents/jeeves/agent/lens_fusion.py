"""Dependence-aware fusion for semantic, cinematic, literary and ludic lenses.

A lens is a hypothesis generator, not an independent sensor. Two lenses can be
beautifully different in vocabulary while relying on the same observation,
evidence artifact or interpretive assumption. Naively multiplying their odds
would create false certainty.

This module therefore fuses *calibrated predictive signals* only after building
an explicit dependence graph. Shared evidence, shared observations, same-lens
reuse and same-family readings are discounted before they can influence a
forecast. Conflicting readings remain visible and can force abstention.

The output interval is a sensitivity envelope, not a frequentist confidence
interval or Bayesian credible interval.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .semantic_lenses import LensFamily
from .semantic_prediction import SemanticForecast
from .types import AgentContractError, json_safe, probability, stable_fingerprint


_EPS = 1e-9


def _logit(p: float) -> float:
    q = min(1.0 - _EPS, max(_EPS, p))
    return math.log(q / (1.0 - q))


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class LensDependenceKind(str, Enum):
    SAME_SIGNAL = "same_signal"
    SAME_LENS = "same_lens"
    SHARED_EVIDENCE = "shared_evidence"
    SHARED_OBSERVATION = "shared_observation"
    SAME_FAMILY = "same_family"
    SHARED_CALIBRATION = "shared_calibration"
    SHARED_PROVENANCE = "shared_provenance"
    EXPLICIT = "explicit"


@dataclass(frozen=True, slots=True)
class LensSignal:
    signal_id: str
    lens_key: str
    family: LensFamily
    probability: float
    confidence: float = 0.5
    ambiguity: float = 0.5
    reliability: float = 0.5
    epistemic_strength: float = 0.5
    observation_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    calibration_group: str = "semantic"
    provenance_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.signal_id).strip() or not str(self.lens_key).strip():
            raise AgentContractError("lens signal requires signal_id and lens_key")
        object.__setattr__(self, "signal_id", str(self.signal_id).strip())
        object.__setattr__(self, "lens_key", str(self.lens_key).strip().casefold())
        if not isinstance(self.family, LensFamily):
            object.__setattr__(self, "family", LensFamily(str(self.family)))
        for name in (
            "probability",
            "confidence",
            "ambiguity",
            "reliability",
            "epistemic_strength",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in ("observation_ids", "evidence_ids", "provenance_ids"):
            object.__setattr__(
                self,
                name,
                tuple(sorted({str(item) for item in getattr(self, name) if str(item)})),
            )
        object.__setattr__(
            self,
            "calibration_group",
            str(self.calibration_group).strip().casefold() or "semantic",
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @classmethod
    def from_forecast(
        cls,
        forecast: SemanticForecast,
        *,
        family: LensFamily,
        confidence: float | None = None,
        reliability: float = 0.5,
    ) -> "LensSignal":
        if not isinstance(forecast, SemanticForecast):
            raise TypeError("forecast must be SemanticForecast")
        lens_key = (
            forecast.source_lens_keys[0]
            if len(forecast.source_lens_keys) == 1
            else "+".join(forecast.source_lens_keys) or "semantic"
        )
        return cls(
            signal_id=forecast.forecast_id,
            lens_key=lens_key,
            family=family,
            probability=forecast.probability,
            confidence=forecast.epistemic_strength if confidence is None else confidence,
            ambiguity=forecast.ambiguity,
            reliability=reliability,
            epistemic_strength=forecast.epistemic_strength,
            observation_ids=forecast.observation_ids,
            evidence_ids=forecast.evidence_ids,
            calibration_group=forecast.calibration_group,
            provenance_ids=tuple(
                sorted(
                    set(forecast.source_finding_ids)
                    | set(forecast.source_interaction_ids)
                )
            ),
            metadata={"forecast_fingerprint": forecast.fingerprint},
        )

    @property
    def raw_weight(self) -> float:
        return (
            self.confidence
            * self.reliability
            * self.epistemic_strength
            * (1.0 - 0.75 * self.ambiguity)
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.signal_id,
                "lens": self.lens_key,
                "family": self.family.value,
                "p": self.probability,
                "confidence": self.confidence,
                "ambiguity": self.ambiguity,
                "reliability": self.reliability,
                "epistemic": self.epistemic_strength,
                "observations": self.observation_ids,
                "evidence": self.evidence_ids,
                "group": self.calibration_group,
                "provenance": self.provenance_ids,
            }
        )


@dataclass(frozen=True, slots=True)
class LensDependence:
    left_id: str
    right_id: str
    kind: LensDependenceKind
    strength: float
    rationale: str
    learned: bool = False

    def __post_init__(self) -> None:
        if self.left_id == self.right_id:
            raise AgentContractError("dependence edge requires distinct signals")
        if not isinstance(self.kind, LensDependenceKind):
            object.__setattr__(self, "kind", LensDependenceKind(str(self.kind)))
        object.__setattr__(self, "strength", probability("dependence strength", self.strength))
        if not str(self.rationale).strip():
            raise AgentContractError("dependence rationale is required")

    @property
    def key(self) -> tuple[str, str]:
        return tuple(sorted((self.left_id, self.right_id)))


@dataclass(frozen=True, slots=True)
class LensFusionPolicy:
    shared_evidence_weight: float = 0.90
    shared_observation_weight: float = 0.80
    same_lens_weight: float = 0.90
    same_family_weight: float = 0.25
    shared_calibration_weight: float = 0.12
    shared_provenance_weight: float = 0.88
    dependence_discount: float = 0.85
    maximum_family_weight: float = 0.80
    maximum_single_weight: float = 0.65
    maximum_log_odds_contribution: float = 2.0
    minimum_total_weight: float = 0.12
    minimum_effective_lenses: float = 1.10
    conflict_threshold: float = 0.55
    ambiguity_shrink: float = 0.55
    sensitivity_radius: float = 1.25

    def __post_init__(self) -> None:
        for name in (
            "shared_evidence_weight",
            "shared_observation_weight",
            "same_lens_weight",
            "same_family_weight",
            "shared_calibration_weight",
            "shared_provenance_weight",
            "dependence_discount",
            "maximum_family_weight",
            "maximum_single_weight",
            "minimum_total_weight",
            "conflict_threshold",
            "ambiguity_shrink",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if self.minimum_effective_lenses < 0:
            raise AgentContractError("minimum_effective_lenses must be non-negative")
        if self.maximum_log_odds_contribution <= 0 or self.sensitivity_radius <= 0:
            raise AgentContractError("fusion radii must be positive")


@dataclass(frozen=True, slots=True)
class LensContribution:
    signal_id: str
    lens_key: str
    family: LensFamily
    raw_weight: float
    redundancy_discount: float
    family_discount: float
    effective_weight: float
    log_odds_delta: float
    contribution: float
    strongest_dependency: float


@dataclass(frozen=True, slots=True)
class LensFusionResult:
    probability: float
    sensitivity_low: float
    sensitivity_high: float
    base_rate: float
    total_effective_weight: float
    effective_lens_count: float
    disagreement: float
    conflict_strength: float
    abstain: bool
    abstention_reasons: tuple[str, ...]
    contributions: tuple[LensContribution, ...]
    dependencies: tuple[LensDependence, ...]
    families: tuple[LensFamily, ...]
    fingerprint: str


class LensFusionEngine:
    """Fuse lens forecasts without counting correlated interpretations twice."""

    def __init__(self, policy: LensFusionPolicy | None = None) -> None:
        self.policy = policy or LensFusionPolicy()

    def infer_dependencies(
        self,
        signals: Sequence[LensSignal],
        *,
        explicit: Sequence[LensDependence] = (),
    ) -> tuple[LensDependence, ...]:
        index: dict[tuple[str, str, LensDependenceKind], LensDependence] = {}
        for edge in explicit:
            index[(edge.key[0], edge.key[1], edge.kind)] = edge

        ordered = tuple(sorted(signals, key=lambda item: item.signal_id))
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                candidates: list[LensDependence] = []
                evidence_overlap = _jaccard(left.evidence_ids, right.evidence_ids)
                if evidence_overlap:
                    candidates.append(
                        LensDependence(
                            left.signal_id,
                            right.signal_id,
                            LensDependenceKind.SHARED_EVIDENCE,
                            min(1.0, self.policy.shared_evidence_weight * evidence_overlap),
                            "signals share factual evidence provenance",
                        )
                    )
                observation_overlap = _jaccard(left.observation_ids, right.observation_ids)
                if observation_overlap:
                    candidates.append(
                        LensDependence(
                            left.signal_id,
                            right.signal_id,
                            LensDependenceKind.SHARED_OBSERVATION,
                            min(
                                1.0,
                                self.policy.shared_observation_weight * observation_overlap,
                            ),
                            "signals reuse the same observation set",
                        )
                    )
                if left.lens_key == right.lens_key:
                    candidates.append(
                        LensDependence(
                            left.signal_id,
                            right.signal_id,
                            LensDependenceKind.SAME_LENS,
                            self.policy.same_lens_weight,
                            "repeated output from the same interpretive lens",
                        )
                    )
                elif left.family is right.family:
                    candidates.append(
                        LensDependence(
                            left.signal_id,
                            right.signal_id,
                            LensDependenceKind.SAME_FAMILY,
                            self.policy.same_family_weight,
                            "signals share a semantic lens family",
                        )
                    )
                if left.calibration_group == right.calibration_group:
                    candidates.append(
                        LensDependence(
                            left.signal_id,
                            right.signal_id,
                            LensDependenceKind.SHARED_CALIBRATION,
                            self.policy.shared_calibration_weight,
                            "signals share a calibration population",
                        )
                    )
                provenance_overlap = _jaccard(left.provenance_ids, right.provenance_ids)
                if provenance_overlap:
                    candidates.append(
                        LensDependence(
                            left.signal_id,
                            right.signal_id,
                            LensDependenceKind.SHARED_PROVENANCE,
                            min(
                                1.0,
                                self.policy.shared_provenance_weight * provenance_overlap,
                            ),
                            "signals descend from shared semantic findings or interactions",
                        )
                    )
                for edge in candidates:
                    key = (edge.key[0], edge.key[1], edge.kind)
                    existing = index.get(key)
                    # Explicit/learned dependence knowledge may be stronger than
                    # a generic overlap heuristic. Never silently weaken it.
                    if existing is None or edge.strength > existing.strength:
                        index[key] = edge
        return tuple(
            sorted(
                index.values(),
                key=lambda edge: (edge.key, edge.kind.value, -edge.strength),
            )
        )

    @staticmethod
    def _dependence_map(
        dependencies: Sequence[LensDependence],
    ) -> Mapping[tuple[str, str], float]:
        result: dict[tuple[str, str], float] = {}
        for edge in dependencies:
            result[edge.key] = max(result.get(edge.key, 0.0), edge.strength)
        return result

    def fuse(
        self,
        signals: Sequence[LensSignal],
        *,
        base_rate: float = 0.5,
        explicit_dependencies: Sequence[LensDependence] = (),
    ) -> LensFusionResult:
        base = probability("base_rate", base_rate)
        if not signals:
            fingerprint = stable_fingerprint({"base": base, "signals": []})
            return LensFusionResult(
                probability=base,
                sensitivity_low=base,
                sensitivity_high=base,
                base_rate=base,
                total_effective_weight=0.0,
                effective_lens_count=0.0,
                disagreement=0.0,
                conflict_strength=0.0,
                abstain=True,
                abstention_reasons=("no_signals",),
                contributions=(),
                dependencies=(),
                families=(),
                fingerprint=fingerprint,
            )
        if any(not isinstance(item, LensSignal) for item in signals):
            raise TypeError("signals must contain LensSignal values")
        if len({item.signal_id for item in signals}) != len(signals):
            raise AgentContractError("signal ids must be unique")

        dependencies = self.infer_dependencies(
            signals, explicit=explicit_dependencies
        )
        dep_map = self._dependence_map(dependencies)
        ordered = sorted(
            signals,
            key=lambda item: (-item.raw_weight, item.family.value, item.signal_id),
        )

        family_used: dict[LensFamily, float] = {}
        accepted: list[LensSignal] = []
        contributions: list[LensContribution] = []
        base_logit = _logit(base)
        fused_logit = base_logit

        for signal in ordered:
            raw = min(self.policy.maximum_single_weight, signal.raw_weight)
            strongest = 0.0
            redundancy = 1.0
            for prior in accepted:
                strength = dep_map.get(
                    tuple(sorted((signal.signal_id, prior.signal_id))), 0.0
                )
                strongest = max(strongest, strength)
                redundancy *= max(
                    0.0, 1.0 - self.policy.dependence_discount * strength
                )
            family_remaining = max(
                0.0,
                self.policy.maximum_family_weight
                - family_used.get(signal.family, 0.0),
            )
            after_redundancy = raw * redundancy
            effective = min(after_redundancy, family_remaining)
            family_discount = (
                0.0 if after_redundancy <= _EPS else effective / after_redundancy
            )
            delta = _logit(signal.probability) - base_logit
            contribution = effective * delta
            contribution = max(
                -self.policy.maximum_log_odds_contribution,
                min(self.policy.maximum_log_odds_contribution, contribution),
            )
            fused_logit += contribution
            family_used[signal.family] = (
                family_used.get(signal.family, 0.0) + effective
            )
            if effective > 0:
                accepted.append(signal)
            contributions.append(
                LensContribution(
                    signal_id=signal.signal_id,
                    lens_key=signal.lens_key,
                    family=signal.family,
                    raw_weight=raw,
                    redundancy_discount=redundancy,
                    family_discount=family_discount,
                    effective_weight=effective,
                    log_odds_delta=delta,
                    contribution=contribution,
                    strongest_dependency=strongest,
                )
            )

        weights = [item.effective_weight for item in contributions if item.effective_weight > 0]
        total_weight = sum(weights)
        effective_count = (
            (total_weight * total_weight) / sum(weight * weight for weight in weights)
            if weights
            else 0.0
        )
        probs = [item.probability for item in ordered]
        signal_weights = [max(_EPS, item.raw_weight) for item in ordered]
        norm = sum(signal_weights)
        mean = sum(w * p for w, p in zip(signal_weights, probs)) / norm
        disagreement = math.sqrt(
            sum(w * (p - mean) ** 2 for w, p in zip(signal_weights, probs)) / norm
        )
        positive_mass = sum(
            contrib.effective_weight
            for item, contrib in zip(ordered, contributions)
            if item.probability > 0.5 and contrib.effective_weight > 0
        )
        negative_mass = sum(
            contrib.effective_weight
            for item, contrib in zip(ordered, contributions)
            if item.probability < 0.5 and contrib.effective_weight > 0
        )
        conflict_strength = (
            min(positive_mass, negative_mass) / max(_EPS, max(positive_mass, negative_mass))
            if positive_mass > 0 and negative_mass > 0
            else 0.0
        )

        average_ambiguity = sum(
            item.ambiguity * max(_EPS, item.raw_weight) for item in ordered
        ) / norm
        shrink = max(
            0.0,
            min(
                1.0,
                (1.0 - self.policy.ambiguity_shrink * average_ambiguity)
                * min(1.0, total_weight),
            ),
        )
        fused = _sigmoid(base_logit + shrink * (fused_logit - base_logit))

        reasons: list[str] = []
        if total_weight < self.policy.minimum_total_weight:
            reasons.append("insufficient_effective_weight")
        if effective_count < self.policy.minimum_effective_lenses:
            reasons.append("insufficient_independent_lenses")
        if conflict_strength >= self.policy.conflict_threshold:
            reasons.append("strong_counter_reading_conflict")
        abstain = bool(reasons)

        radius = self.policy.sensitivity_radius * (
            1.0 + disagreement + conflict_strength
        ) / math.sqrt(max(1.0, effective_count + total_weight))
        sensitivity_low = _sigmoid(_logit(fused) - radius)
        sensitivity_high = _sigmoid(_logit(fused) + radius)

        fingerprint = stable_fingerprint(
            {
                "base": base,
                "signals": [item.fingerprint for item in ordered],
                "dependencies": [
                    (edge.key, edge.kind.value, edge.strength) for edge in dependencies
                ],
                "contributions": [
                    (
                        item.signal_id,
                        item.effective_weight,
                        item.contribution,
                        item.strongest_dependency,
                    )
                    for item in contributions
                ],
                "probability": fused,
                "sensitivity": (sensitivity_low, sensitivity_high),
                "abstain": reasons,
            }
        )
        return LensFusionResult(
            probability=fused,
            sensitivity_low=sensitivity_low,
            sensitivity_high=sensitivity_high,
            base_rate=base,
            total_effective_weight=total_weight,
            effective_lens_count=effective_count,
            disagreement=disagreement,
            conflict_strength=conflict_strength,
            abstain=abstain,
            abstention_reasons=tuple(reasons),
            contributions=tuple(contributions),
            dependencies=dependencies,
            families=tuple(
                sorted({item.family for item in ordered}, key=lambda family: family.value)
            ),
            fingerprint=fingerprint,
        )
