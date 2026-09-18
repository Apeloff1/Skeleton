"""Advanced uncertainty, calibration, and forecast evaluation for Jeeves.

This module extends ``probability_lenses`` without replacing its deliberately
small engineering taxonomy.  Its purpose is to keep *different meanings of
uncertainty separate* while still giving the runtime a common evaluation and
routing surface.

Design rules
------------
1. A probability, a coverage guarantee, a risk functional, an information
   quantity, and an abstention decision are not interchangeable scalars.
2. Calibration and sharpness are tracked separately.  A sharp forecast that is
   miscalibrated is not rewarded for being confidently wrong.
3. Proper scoring rules evaluate forecasts; they do not magically prove a
   predictive model is correctly specified or stable under distribution shift.
4. Conformal guarantees carry their exchangeability/calibration assumptions in
   the output contract.  Out-of-distribution signals can therefore force
   abstention rather than silently inheriting an invalid coverage claim.
5. Language-model uncertainty is multidimensional: input ambiguity, semantic
   answer diversity, reasoning-path disagreement, model/parameter uncertainty,
   retrieval uncertainty, and distribution shift are represented independently.
6. Downstream policy sees a vector.  Scalarization is explicit, task-specific,
   risk-sensitive, and auditable.

All algorithms here are dependency-free reference implementations intended for
replay, testing, and host-side policy.  Expensive statistical estimators can be
plugged in later behind the same contracts.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .types import AgentContractError, finite_number, json_safe, positive_int, probability, stable_fingerprint

_EPS = 1e-15


class AdvancedUncertaintyError(AgentContractError):
    pass


class UncertaintyAxis(str, Enum):
    ALEATORIC = "aleatoric"
    EPISTEMIC = "epistemic"
    INPUT = "input"
    SEMANTIC = "semantic"
    REASONING_PATH = "reasoning_path"
    PARAMETER = "parameter"
    RETRIEVAL = "retrieval"
    CAUSAL_IDENTIFICATION = "causal_identification"
    DISTRIBUTION_SHIFT = "distribution_shift"
    TEMPORAL_DRIFT = "temporal_drift"
    TAIL = "tail"
    ADVERSARIAL = "adversarial"
    CALIBRATION = "calibration"
    COVERAGE = "coverage"
    DECISION = "decision"


class AdvancedLens(str, Enum):
    PREDICTIVE_ENTROPY = "predictive_entropy"
    EXPECTED_ENTROPY = "expected_entropy"
    MUTUAL_INFORMATION = "mutual_information"
    ENSEMBLE_DISAGREEMENT = "ensemble_disagreement"
    SEMANTIC_ENTROPY = "semantic_entropy"
    PROMPT_SENSITIVITY = "prompt_sensitivity"
    REASONING_PATH_DIVERGENCE = "reasoning_path_divergence"
    RETRIEVAL_DISAGREEMENT = "retrieval_disagreement"
    POSTERIOR_PREDICTIVE_CHECK = "posterior_predictive_check"
    CONFORMAL_COVERAGE = "conformal_coverage"
    CONFORMAL_RISK = "conformal_risk"
    SELECTIVE_ABSTENTION = "selective_abstention"
    CALIBRATION_ERROR = "calibration_error"
    SHARPNESS = "sharpness"
    BRIER = "brier"
    LOG_SCORE = "log_score"
    CRPS = "crps"
    TAIL_CALIBRATION = "tail_calibration"
    QUANTILE_LOSS = "quantile_loss"
    EXPECTILE_LOSS = "expectile_loss"
    CVAR = "cvar"
    ENTROPIC_RISK = "entropic_risk"
    MINIMAX_REGRET = "minimax_regret"
    DISTRIBUTIONAL_ROBUSTNESS = "distributional_robustness"
    VALUE_OF_INFORMATION = "value_of_information"
    INFORMATION_GAIN = "information_gain"
    INFORMATION_DIRECTED = "information_directed"
    BAYESIAN_MODEL_AVERAGING = "bayesian_model_averaging"
    PAC_BAYES_COMPLEXITY = "pac_bayes_complexity"
    OOD_SCORE = "ood_score"
    DRIFT_SCORE = "drift_score"
    IDENTIFICATION_GAP = "identification_gap"
    MEMORY_RECALL_RISK = "memory_recall_risk"
    GAME_MONTE_CARLO_ERROR = "game_monte_carlo_error"


class MetricOrientation(str, Enum):
    LOWER_BETTER = "lower_better"
    HIGHER_BETTER = "higher_better"
    TARGET = "target"
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True, slots=True)
class LensContract:
    lens: AdvancedLens
    axes: tuple[UncertaintyAxis, ...]
    lineage_year: int
    orientation: MetricOrientation
    description: str
    use_when: str
    invalid_when: str
    supports_decision_scalarization: bool = False
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.lens, AdvancedLens):
            object.__setattr__(self, "lens", AdvancedLens(str(self.lens)))
        axes = tuple(axis if isinstance(axis, UncertaintyAxis) else UncertaintyAxis(str(axis)) for axis in self.axes)
        if not axes:
            raise AdvancedUncertaintyError("lens contract requires uncertainty axes")
        object.__setattr__(self, "axes", axes)
        if not isinstance(self.lineage_year, int) or isinstance(self.lineage_year, bool):
            raise AdvancedUncertaintyError("lineage_year must be integer")
        if not isinstance(self.orientation, MetricOrientation):
            object.__setattr__(self, "orientation", MetricOrientation(str(self.orientation)))
        object.__setattr__(self, "tags", tuple(sorted({str(tag).casefold() for tag in self.tags if str(tag).strip()})))


@dataclass(frozen=True, slots=True)
class LensMeasurement:
    lens: AdvancedLens
    value: float
    axes: tuple[UncertaintyAxis, ...]
    normalized_risk: float | None = None
    sample_size: float | None = None
    calibrated: bool | None = None
    valid: bool = True
    assumptions: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.lens, AdvancedLens):
            object.__setattr__(self, "lens", AdvancedLens(str(self.lens)))
        value = finite_number("measurement value", self.value)
        object.__setattr__(self, "value", value)
        axes = tuple(axis if isinstance(axis, UncertaintyAxis) else UncertaintyAxis(str(axis)) for axis in self.axes)
        if not axes:
            raise AdvancedUncertaintyError("measurement requires axes")
        object.__setattr__(self, "axes", axes)
        if self.normalized_risk is not None:
            object.__setattr__(self, "normalized_risk", probability("normalized_risk", self.normalized_risk))
        if self.sample_size is not None:
            n = finite_number("sample_size", self.sample_size)
            if n < 0:
                raise AdvancedUncertaintyError("sample_size must be non-negative")
            object.__setattr__(self, "sample_size", n)
        object.__setattr__(self, "assumptions", tuple(sorted({str(item) for item in self.assumptions if str(item)})))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(item) for item in self.evidence_ids if str(item)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "lens": self.lens.value,
                "value": self.value,
                "axes": [axis.value for axis in self.axes],
                "risk": self.normalized_risk,
                "n": self.sample_size,
                "calibrated": self.calibrated,
                "valid": self.valid,
                "assumptions": self.assumptions,
                "evidence": self.evidence_ids,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True, slots=True)
class ForecastCase:
    probability: float
    outcome: bool
    weight: float = 1.0
    group: str = "default"
    timestamp: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "probability", probability("forecast probability", self.probability))
        weight = finite_number("forecast weight", self.weight)
        if weight <= 0:
            raise AdvancedUncertaintyError("forecast weight must be positive")
        object.__setattr__(self, "weight", weight)
        object.__setattr__(self, "group", str(self.group))
        if self.timestamp is not None:
            object.__setattr__(self, "timestamp", finite_number("timestamp", self.timestamp))


@dataclass(frozen=True, slots=True)
class ForecastEvaluation:
    count: int
    weight_sum: float
    brier: float
    log_score: float
    ece: float
    mce: float
    sharpness_variance: float
    resolution: float
    reliability: float
    base_rate: float
    tail_ece: float | None
    bin_count: int
    fingerprint: str


class ProperScoring:
    """Reference proper/scoring-rule calculations for binary forecasts."""

    @staticmethod
    def brier(cases: Sequence[ForecastCase]) -> float:
        if not cases:
            raise AdvancedUncertaintyError("Brier score requires forecasts")
        total = sum(case.weight for case in cases)
        return sum(case.weight * (case.probability - float(case.outcome)) ** 2 for case in cases) / total

    @staticmethod
    def log_score(cases: Sequence[ForecastCase]) -> float:
        if not cases:
            raise AdvancedUncertaintyError("log score requires forecasts")
        total = sum(case.weight for case in cases)
        loss = 0.0
        for case in cases:
            p = min(1.0 - _EPS, max(_EPS, case.probability))
            loss += case.weight * (-(math.log(p) if case.outcome else math.log(1.0 - p)))
        return loss / total

    @staticmethod
    def crps_empirical(samples: Sequence[float], observation: float) -> float:
        """CRPS for an empirical predictive distribution.

        Uses E|X-y| - 1/2 E|X-X'|.  O(n^2) is deliberate here because this is a
        transparent reference implementation; production adapters can replace it
        with sorted O(n log n) implementations without changing semantics.
        """
        if not samples:
            raise AdvancedUncertaintyError("CRPS requires predictive samples")
        xs = [finite_number("sample", item) for item in samples]
        y = finite_number("observation", observation)
        first = sum(abs(x - y) for x in xs) / len(xs)
        pair = sum(abs(x - z) for x in xs for z in xs) / (len(xs) * len(xs))
        return first - 0.5 * pair

    @staticmethod
    def pinball(quantile_prediction: float, observation: float, *, tau: float) -> float:
        q = finite_number("quantile_prediction", quantile_prediction)
        y = finite_number("observation", observation)
        tau = probability("tau", tau)
        if tau in {0.0, 1.0}:
            raise AdvancedUncertaintyError("quantile tau must be in (0,1)")
        error = y - q
        return max(tau * error, (tau - 1.0) * error)

    @staticmethod
    def expectile_loss(expectile_prediction: float, observation: float, *, tau: float) -> float:
        prediction = finite_number("expectile_prediction", expectile_prediction)
        y = finite_number("observation", observation)
        tau = probability("tau", tau)
        if tau in {0.0, 1.0}:
            raise AdvancedUncertaintyError("expectile tau must be in (0,1)")
        residual = y - prediction
        weight = tau if residual >= 0 else 1.0 - tau
        return weight * residual * residual


class CalibrationDiagnostics:
    @staticmethod
    def evaluate(cases: Sequence[ForecastCase], *, bins: int = 10, tail_threshold: float = 0.9) -> ForecastEvaluation:
        if not cases:
            raise AdvancedUncertaintyError("calibration evaluation requires forecasts")
        bins = positive_int("bins", bins, maximum=1000)
        tail_threshold = probability("tail_threshold", tail_threshold)
        if tail_threshold <= 0.5 or tail_threshold >= 1.0:
            raise AdvancedUncertaintyError("tail_threshold must be in (0.5,1)")
        total_weight = sum(case.weight for case in cases)
        base_rate = sum(case.weight * float(case.outcome) for case in cases) / total_weight
        groups: defaultdict[int, list[ForecastCase]] = defaultdict(list)
        for case in cases:
            index = min(bins - 1, int(case.probability * bins))
            groups[index].append(case)

        ece = 0.0
        mce = 0.0
        reliability = 0.0
        resolution = 0.0
        mean_probability = sum(case.weight * case.probability for case in cases) / total_weight
        sharpness = sum(case.weight * (case.probability - mean_probability) ** 2 for case in cases) / total_weight
        for bucket in groups.values():
            weight = sum(case.weight for case in bucket)
            confidence = sum(case.weight * case.probability for case in bucket) / weight
            accuracy = sum(case.weight * float(case.outcome) for case in bucket) / weight
            gap = abs(confidence - accuracy)
            ece += (weight / total_weight) * gap
            mce = max(mce, gap)
            reliability += (weight / total_weight) * (confidence - accuracy) ** 2
            resolution += (weight / total_weight) * (accuracy - base_rate) ** 2

        tail_cases = [case for case in cases if case.probability >= tail_threshold or case.probability <= 1.0 - tail_threshold]
        tail_ece = None
        if tail_cases:
            tail_weight = sum(case.weight for case in tail_cases)
            tail_ece = sum(case.weight * abs(case.probability - float(case.outcome)) for case in tail_cases) / tail_weight
        payload = {
            "count": len(cases),
            "weight": total_weight,
            "brier": ProperScoring.brier(cases),
            "log_score": ProperScoring.log_score(cases),
            "ece": ece,
            "mce": mce,
            "sharpness": sharpness,
            "resolution": resolution,
            "reliability": reliability,
            "base_rate": base_rate,
            "tail_ece": tail_ece,
            "bins": bins,
        }
        return ForecastEvaluation(
            count=len(cases),
            weight_sum=total_weight,
            brier=payload["brier"],
            log_score=payload["log_score"],
            ece=ece,
            mce=mce,
            sharpness_variance=sharpness,
            resolution=resolution,
            reliability=reliability,
            base_rate=base_rate,
            tail_ece=tail_ece,
            bin_count=bins,
            fingerprint=stable_fingerprint(payload),
        )


@dataclass(frozen=True, slots=True)
class ConformalExample:
    nonconformity: float
    correct: bool = True
    weight: float = 1.0

    def __post_init__(self) -> None:
        value = finite_number("nonconformity", self.nonconformity)
        if value < 0:
            raise AdvancedUncertaintyError("nonconformity must be non-negative")
        object.__setattr__(self, "nonconformity", value)
        weight = finite_number("weight", self.weight)
        if weight <= 0:
            raise AdvancedUncertaintyError("weight must be positive")
        object.__setattr__(self, "weight", weight)


@dataclass(frozen=True, slots=True)
class ConformalThreshold:
    alpha: float
    threshold: float
    calibration_size: int
    nominal_coverage: float
    exchangeability_assumed: bool
    fingerprint: str


class ConformalControl:
    """Transparent split-conformal thresholding plus shift-aware abstention."""

    @staticmethod
    def threshold(calibration: Sequence[ConformalExample], *, alpha: float = 0.1) -> ConformalThreshold:
        if not calibration:
            raise AdvancedUncertaintyError("conformal calibration set is empty")
        alpha = probability("alpha", alpha)
        if alpha <= 0.0 or alpha >= 1.0:
            raise AdvancedUncertaintyError("alpha must be in (0,1)")
        # Standard finite-sample split-conformal rank: ceil((n+1)(1-alpha)).
        # We intentionally ignore weights in this reference threshold; weighted
        # conformal requires a different validity argument and must use another adapter.
        values = sorted(item.nonconformity for item in calibration)
        n = len(values)
        rank = min(n, max(1, math.ceil((n + 1) * (1.0 - alpha))))
        value = values[rank - 1]
        payload = {"alpha": alpha, "n": n, "rank": rank, "threshold": value}
        return ConformalThreshold(alpha, value, n, 1.0 - alpha, True, stable_fingerprint(payload))

    @staticmethod
    def accept(score: float, threshold: ConformalThreshold) -> bool:
        value = finite_number("nonconformity score", score)
        return value <= threshold.threshold


@dataclass(frozen=True, slots=True)
class ShiftSignal:
    score: float
    threshold: float
    shifted: bool
    method: str
    sample_size: int
    fingerprint: str


class DistributionShift:
    @staticmethod
    def population_stability_index(reference: Sequence[float], current: Sequence[float], *, bins: int = 10) -> ShiftSignal:
        """Compute a bounded PSI-derived shift signal for scalar features.

        PSI is a heuristic drift diagnostic, not a hypothesis-test p-value.  The
        returned score is transformed to ``1-exp(-PSI)`` only for routing.
        """
        if not reference or not current:
            raise AdvancedUncertaintyError("drift comparison needs reference and current samples")
        bins = positive_int("bins", bins, maximum=1000)
        ref = sorted(finite_number("reference value", x) for x in reference)
        cur = [finite_number("current value", x) for x in current]
        low = min(ref[0], min(cur))
        high = max(ref[-1], max(cur))
        if high <= low:
            payload = {"psi": 0.0, "score": 0.0, "n": len(cur), "bins": bins}
            return ShiftSignal(0.0, 0.25, False, "psi", len(cur), stable_fingerprint(payload))
        width = (high - low) / bins
        ref_counts = [0] * bins
        cur_counts = [0] * bins
        for value in ref:
            ref_counts[min(bins - 1, int((value - low) / width))] += 1
        for value in cur:
            cur_counts[min(bins - 1, int((value - low) / width))] += 1
        psi = 0.0
        for r_count, c_count in zip(ref_counts, cur_counts):
            r = max(_EPS, r_count / len(ref))
            c = max(_EPS, c_count / len(cur))
            psi += (c - r) * math.log(c / r)
        score = 1.0 - math.exp(-max(0.0, psi))
        threshold = 1.0 - math.exp(-0.25)
        payload = {"psi": psi, "score": score, "threshold": threshold, "n": len(cur), "bins": bins}
        return ShiftSignal(score, threshold, score >= threshold, "psi", len(cur), stable_fingerprint(payload))


@dataclass(frozen=True, slots=True)
class SemanticCluster:
    cluster_id: str
    probability_mass: float
    member_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not str(self.cluster_id).strip():
            raise AdvancedUncertaintyError("semantic cluster requires id")
        object.__setattr__(self, "probability_mass", probability("probability_mass", self.probability_mass))
        members = tuple(sorted({str(item) for item in self.member_ids if str(item)}))
        if not members:
            raise AdvancedUncertaintyError("semantic cluster requires members")
        object.__setattr__(self, "member_ids", members)


class InformationDiagnostics:
    @staticmethod
    def entropy(probabilities: Sequence[float], *, base: float = 2.0) -> float:
        if not probabilities:
            raise AdvancedUncertaintyError("entropy requires probabilities")
        ps = [probability("probability", p) for p in probabilities]
        total = sum(ps)
        if total <= 0:
            raise AdvancedUncertaintyError("probability mass sums to zero")
        log_base = math.log(base)
        return -sum((p / total) * math.log(max(_EPS, p / total)) / log_base for p in ps if p > 0)

    @classmethod
    def semantic_entropy(cls, clusters: Sequence[SemanticCluster]) -> LensMeasurement:
        if not clusters:
            raise AdvancedUncertaintyError("semantic entropy requires clusters")
        masses = [cluster.probability_mass for cluster in clusters]
        entropy = cls.entropy(masses)
        maximum = math.log(max(1, len(clusters)), 2) if len(clusters) > 1 else 0.0
        normalized = 0.0 if maximum <= 0 else min(1.0, entropy / maximum)
        return LensMeasurement(
            AdvancedLens.SEMANTIC_ENTROPY,
            entropy,
            (UncertaintyAxis.SEMANTIC, UncertaintyAxis.EPISTEMIC),
            normalized_risk=normalized,
            sample_size=float(sum(len(cluster.member_ids) for cluster in clusters)),
            assumptions=("semantic equivalence clustering is valid",),
            metadata={"cluster_count": len(clusters), "normalized_entropy": normalized},
        )

    @classmethod
    def mutual_information_from_ensemble(cls, member_distributions: Sequence[Sequence[float]]) -> LensMeasurement:
        if not member_distributions:
            raise AdvancedUncertaintyError("ensemble MI requires member distributions")
        width = len(member_distributions[0])
        if width == 0 or any(len(row) != width for row in member_distributions):
            raise AdvancedUncertaintyError("ensemble distributions must have same non-zero support")
        normalized_rows: list[list[float]] = []
        for row in member_distributions:
            values = [probability("ensemble probability", x) for x in row]
            total = sum(values)
            if total <= 0:
                raise AdvancedUncertaintyError("ensemble member mass sums to zero")
            normalized_rows.append([x / total for x in values])
        mean = [sum(row[i] for row in normalized_rows) / len(normalized_rows) for i in range(width)]
        predictive = cls.entropy(mean)
        expected = sum(cls.entropy(row) for row in normalized_rows) / len(normalized_rows)
        mi = max(0.0, predictive - expected)
        maximum = math.log(width, 2) if width > 1 else 0.0
        normalized = 0.0 if maximum <= 0 else min(1.0, mi / maximum)
        return LensMeasurement(
            AdvancedLens.MUTUAL_INFORMATION,
            mi,
            (UncertaintyAxis.EPISTEMIC, UncertaintyAxis.PARAMETER),
            normalized_risk=normalized,
            sample_size=float(len(normalized_rows)),
            metadata={"predictive_entropy": predictive, "expected_entropy": expected, "support": width},
        )


class RiskDiagnostics:
    @staticmethod
    def cvar(losses: Sequence[float], *, alpha: float = 0.95) -> LensMeasurement:
        if not losses:
            raise AdvancedUncertaintyError("CVaR requires losses")
        alpha = probability("alpha", alpha)
        if alpha <= 0.0 or alpha >= 1.0:
            raise AdvancedUncertaintyError("CVaR alpha must be in (0,1)")
        values = sorted(finite_number("loss", loss) for loss in losses)
        if any(value < 0 for value in values):
            raise AdvancedUncertaintyError("reference CVaR expects non-negative losses")
        rank = min(len(values) - 1, max(0, math.ceil(alpha * len(values)) - 1))
        tail = values[rank:]
        value = sum(tail) / len(tail)
        scale = max(_EPS, max(values))
        return LensMeasurement(
            AdvancedLens.CVAR,
            value,
            (UncertaintyAxis.TAIL, UncertaintyAxis.DECISION),
            normalized_risk=min(1.0, value / scale),
            sample_size=float(len(values)),
            metadata={"alpha": alpha, "tail_count": len(tail)},
        )

    @staticmethod
    def entropic_risk(losses: Sequence[float], *, risk_aversion: float = 1.0) -> LensMeasurement:
        if not losses:
            raise AdvancedUncertaintyError("entropic risk requires losses")
        eta = finite_number("risk_aversion", risk_aversion)
        if eta <= 0:
            raise AdvancedUncertaintyError("risk_aversion must be positive")
        values = [finite_number("loss", loss) for loss in losses]
        maximum = max(values)
        # log-sum-exp stabilization.
        mean_exp = sum(math.exp(eta * (value - maximum)) for value in values) / len(values)
        result = maximum + math.log(max(_EPS, mean_exp)) / eta
        spread = max(_EPS, max(values) - min(values))
        return LensMeasurement(
            AdvancedLens.ENTROPIC_RISK,
            result,
            (UncertaintyAxis.TAIL, UncertaintyAxis.DECISION),
            normalized_risk=min(1.0, max(0.0, result - min(values)) / spread),
            sample_size=float(len(values)),
            metadata={"risk_aversion": eta},
        )

    @staticmethod
    def minimax_regret(utilities_by_model: Sequence[Sequence[float]]) -> tuple[int, LensMeasurement]:
        if not utilities_by_model:
            raise AdvancedUncertaintyError("minimax regret requires model utilities")
        action_count = len(utilities_by_model[0])
        if action_count == 0 or any(len(row) != action_count for row in utilities_by_model):
            raise AdvancedUncertaintyError("utility matrix must be rectangular and non-empty")
        rows = [[finite_number("utility", value) for value in row] for row in utilities_by_model]
        worst_regrets: list[float] = []
        for action in range(action_count):
            regrets = [max(row) - row[action] for row in rows]
            worst_regrets.append(max(regrets))
        chosen = min(range(action_count), key=lambda idx: (worst_regrets[idx], idx))
        maximum = max(_EPS, max(worst_regrets))
        measurement = LensMeasurement(
            AdvancedLens.MINIMAX_REGRET,
            worst_regrets[chosen],
            (UncertaintyAxis.ADVERSARIAL, UncertaintyAxis.DECISION, UncertaintyAxis.EPISTEMIC),
            normalized_risk=min(1.0, worst_regrets[chosen] / maximum),
            sample_size=float(len(rows)),
            metadata={"chosen_action": chosen, "worst_regret_by_action": worst_regrets},
        )
        return chosen, measurement


@dataclass(frozen=True, slots=True)
class UncertaintyProfile:
    measurements: tuple[LensMeasurement, ...]
    axis_risk: Mapping[str, float]
    invalid_lenses: tuple[str, ...]
    dominant_axes: tuple[str, ...]
    fingerprint: str


class UncertaintyProfiler:
    """Aggregate only within axes; never erase the measurement vector."""

    @staticmethod
    def build(measurements: Sequence[LensMeasurement]) -> UncertaintyProfile:
        if not measurements:
            payload = {"measurements": []}
            return UncertaintyProfile((), {}, (), (), stable_fingerprint(payload))
        axis_values: defaultdict[UncertaintyAxis, list[float]] = defaultdict(list)
        invalid: list[str] = []
        for measurement in measurements:
            if not measurement.valid:
                invalid.append(measurement.lens.value)
                continue
            if measurement.normalized_risk is None:
                continue
            for axis in measurement.axes:
                axis_values[axis].append(measurement.normalized_risk)
        # Conservative noisy-OR: multiple independent-looking warnings cannot
        # cancel each other as a mean would.  Correlation is not assumed away;
        # the vector is retained for downstream inspection.
        axis_risk: dict[str, float] = {}
        for axis, values in axis_values.items():
            survival = 1.0
            for value in values:
                survival *= 1.0 - min(0.999999999, value)
            axis_risk[axis.value] = 1.0 - survival
        dominant = tuple(key for key, _ in sorted(axis_risk.items(), key=lambda item: (-item[1], item[0]))[:5])
        payload = {
            "measurements": [measurement.fingerprint for measurement in measurements],
            "axis_risk": axis_risk,
            "invalid": sorted(invalid),
            "dominant": dominant,
        }
        return UncertaintyProfile(tuple(measurements), axis_risk, tuple(sorted(invalid)), dominant, stable_fingerprint(payload))


@dataclass(frozen=True, slots=True)
class AbstentionPolicy:
    maximum_axis_risk: float = 0.78
    maximum_shift_risk: float = 0.55
    maximum_semantic_risk: float = 0.72
    maximum_tail_risk: float = 0.80
    minimum_utility_margin: float = 0.05

    def __post_init__(self) -> None:
        for name in ("maximum_axis_risk", "maximum_shift_risk", "maximum_semantic_risk", "maximum_tail_risk", "minimum_utility_margin"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class AbstentionDecision:
    abstain: bool
    reason: str
    profile_fingerprint: str
    violated_axes: tuple[str, ...]
    utility_margin: float


class SelectivePrediction:
    @staticmethod
    def decide(profile: UncertaintyProfile, *, utility_margin: float, policy: AbstentionPolicy | None = None) -> AbstentionDecision:
        policy = policy or AbstentionPolicy()
        margin = finite_number("utility_margin", utility_margin)
        if margin < 0:
            raise AdvancedUncertaintyError("utility_margin must be non-negative")
        violated: list[str] = []
        for axis, risk in profile.axis_risk.items():
            limit = policy.maximum_axis_risk
            if axis in {UncertaintyAxis.DISTRIBUTION_SHIFT.value, UncertaintyAxis.TEMPORAL_DRIFT.value}:
                limit = policy.maximum_shift_risk
            elif axis == UncertaintyAxis.SEMANTIC.value:
                limit = policy.maximum_semantic_risk
            elif axis == UncertaintyAxis.TAIL.value:
                limit = policy.maximum_tail_risk
            if risk > limit:
                violated.append(axis)
        if profile.invalid_lenses:
            return AbstentionDecision(True, "one or more uncertainty contracts are invalid", profile.fingerprint, tuple(sorted(violated)), margin)
        if violated:
            return AbstentionDecision(True, "uncertainty risk exceeds policy", profile.fingerprint, tuple(sorted(violated)), margin)
        if margin < policy.minimum_utility_margin:
            return AbstentionDecision(True, "best action lacks sufficient utility margin", profile.fingerprint, (), margin)
        return AbstentionDecision(False, "risk and decision margin satisfy policy", profile.fingerprint, (), margin)


class LensRegistry:
    def __init__(self, contracts: Iterable[LensContract] = ()) -> None:
        self._contracts: dict[AdvancedLens, LensContract] = {contract.lens: contract for contract in default_lens_contracts()}
        for contract in contracts:
            self._contracts[contract.lens] = contract

    def get(self, lens: AdvancedLens) -> LensContract:
        return self._contracts[lens if isinstance(lens, AdvancedLens) else AdvancedLens(str(lens))]

    def all(self) -> tuple[LensContract, ...]:
        return tuple(sorted(self._contracts.values(), key=lambda item: (item.lineage_year, item.lens.value)))

    def by_axis(self, axis: UncertaintyAxis) -> tuple[LensContract, ...]:
        return tuple(contract for contract in self.all() if axis in contract.axes)


def _contract(
    lens: AdvancedLens,
    axes: Sequence[UncertaintyAxis],
    year: int,
    orientation: MetricOrientation,
    description: str,
    use_when: str,
    invalid_when: str,
    *,
    scalar: bool = False,
    tags: Sequence[str] = (),
) -> LensContract:
    return LensContract(lens, tuple(axes), year, orientation, description, use_when, invalid_when, scalar, tuple(tags))


def default_lens_contracts() -> tuple[LensContract, ...]:
    return (
        _contract(AdvancedLens.PREDICTIVE_ENTROPY, (UncertaintyAxis.ALEATORIC, UncertaintyAxis.EPISTEMIC), 1948, MetricOrientation.DIAGNOSTIC, "Entropy of the predictive distribution.", "Total predictive uncertainty matters.", "Support/probabilities are not normalized."),
        _contract(AdvancedLens.EXPECTED_ENTROPY, (UncertaintyAxis.ALEATORIC,), 1948, MetricOrientation.DIAGNOSTIC, "Expected within-model entropy.", "Separating irreducible outcome uncertainty from model disagreement.", "Ensemble members are not comparable distributions."),
        _contract(AdvancedLens.MUTUAL_INFORMATION, (UncertaintyAxis.EPISTEMIC, UncertaintyAxis.PARAMETER), 1948, MetricOrientation.LOWER_BETTER, "Predictive entropy minus expected member entropy.", "Ensemble/posterior disagreement is meaningful.", "Members are duplicates or not posterior/model samples."),
        _contract(AdvancedLens.ENSEMBLE_DISAGREEMENT, (UncertaintyAxis.EPISTEMIC,), 1990, MetricOrientation.LOWER_BETTER, "Dispersion across predictive models.", "Multiple independently useful models exist.", "Shared training/data makes naive independence assumptions invalid."),
        _contract(AdvancedLens.SEMANTIC_ENTROPY, (UncertaintyAxis.SEMANTIC, UncertaintyAxis.EPISTEMIC), 2024, MetricOrientation.LOWER_BETTER, "Entropy over meaning-equivalence classes rather than strings.", "Free-form outputs contain paraphrases and genuinely different answers.", "Semantic clustering/entailment is unreliable.", tags=("language", "meaning")),
        _contract(AdvancedLens.PROMPT_SENSITIVITY, (UncertaintyAxis.INPUT, UncertaintyAxis.SEMANTIC), 2025, MetricOrientation.LOWER_BETTER, "Variation in meaning-level predictions under semantically compatible prompt variants.", "Robustness to wording/framing matters.", "Prompt variants change the task semantics."),
        _contract(AdvancedLens.REASONING_PATH_DIVERGENCE, (UncertaintyAxis.REASONING_PATH, UncertaintyAxis.EPISTEMIC), 2025, MetricOrientation.LOWER_BETTER, "Disagreement among independently generated reasoning trajectories.", "Multiple reasoning routes are available.", "Routes are copied/correlated or final answer equivalence is ignored."),
        _contract(AdvancedLens.RETRIEVAL_DISAGREEMENT, (UncertaintyAxis.RETRIEVAL,), 2023, MetricOrientation.LOWER_BETTER, "Instability across retrieved evidence sets.", "RAG/context retrieval influences the answer.", "Retrieval samples are not meaningfully perturbed."),
        _contract(AdvancedLens.POSTERIOR_PREDICTIVE_CHECK, (UncertaintyAxis.EPISTEMIC,), 1980, MetricOrientation.DIAGNOSTIC, "Compare observed diagnostics with data replicated from the fitted model.", "Model adequacy matters beyond parameter fit.", "Check statistic is selected after seeing failure without correction."),
        _contract(AdvancedLens.CONFORMAL_COVERAGE, (UncertaintyAxis.COVERAGE,), 1998, MetricOrientation.TARGET, "Finite-sample prediction-set coverage under conformal assumptions.", "Set-valued predictions are useful and calibration data are exchangeable.", "Exchangeability/score validity is materially violated.", tags=("coverage",)),
        _contract(AdvancedLens.CONFORMAL_RISK, (UncertaintyAxis.COVERAGE, UncertaintyAxis.DECISION), 2020, MetricOrientation.TARGET, "Conformal calibration of a user-defined risk/loss.", "A task loss can be calibrated rather than only set coverage.", "Calibration assumptions or loss contract are invalid."),
        _contract(AdvancedLens.SELECTIVE_ABSTENTION, (UncertaintyAxis.DECISION,), 2025, MetricOrientation.DIAGNOSTIC, "Route uncertain cases to set prediction or abstention according to utility/risk.", "Wrong confident output costs more than deferral.", "Abstention itself has unmodeled or prohibitive cost.", scalar=True),
        _contract(AdvancedLens.CALIBRATION_ERROR, (UncertaintyAxis.CALIBRATION,), 1980, MetricOrientation.LOWER_BETTER, "Mismatch between predicted probabilities and empirical outcome frequencies.", "Forecast probabilities are used operationally.", "Bins/groups are too sparse or selection changes the evaluated population."),
        _contract(AdvancedLens.SHARPNESS, (UncertaintyAxis.CALIBRATION,), 1987, MetricOrientation.HIGHER_BETTER, "Concentration/refinement of forecasts, evaluated subject to calibration.", "Comparing informative calibrated forecasters.", "Used without calibration/reliability checks."),
        _contract(AdvancedLens.BRIER, (UncertaintyAxis.CALIBRATION,), 1950, MetricOrientation.LOWER_BETTER, "Proper quadratic score for probabilistic forecasts.", "Binary/categorical probability quality is evaluated.", "Compared across incompatible outcome definitions."),
        _contract(AdvancedLens.LOG_SCORE, (UncertaintyAxis.CALIBRATION, UncertaintyAxis.TAIL), 1950, MetricOrientation.LOWER_BETTER, "Strictly proper logarithmic score with strong penalty for unsupported outcomes.", "Full predictive density/probabilities are available.", "Zero probabilities are artifacts of finite precision/model truncation."),
        _contract(AdvancedLens.CRPS, (UncertaintyAxis.CALIBRATION,), 1970, MetricOrientation.LOWER_BETTER, "Proper score comparing a univariate predictive CDF with an observation.", "Continuous probabilistic forecasts are evaluated.", "Variables/scales are incomparable without normalization."),
        _contract(AdvancedLens.TAIL_CALIBRATION, (UncertaintyAxis.TAIL, UncertaintyAxis.CALIBRATION), 2025, MetricOrientation.LOWER_BETTER, "Calibration focused on extreme predictive regions.", "Rare/high-impact outcomes matter.", "Tail sample size is insufficient."),
        _contract(AdvancedLens.QUANTILE_LOSS, (UncertaintyAxis.TAIL,), 1978, MetricOrientation.LOWER_BETTER, "Pinball loss for quantile forecasts.", "Specific predictive quantiles drive decisions.", "Quantile crossing or wrong target quantile."),
        _contract(AdvancedLens.EXPECTILE_LOSS, (UncertaintyAxis.TAIL,), 1976, MetricOrientation.LOWER_BETTER, "Asymmetric squared loss eliciting expectiles.", "Tail-sensitive smooth point functionals are useful.", "Expectile is misread as a quantile."),
        _contract(AdvancedLens.CVAR, (UncertaintyAxis.TAIL, UncertaintyAxis.DECISION), 2000, MetricOrientation.LOWER_BETTER, "Expected loss in a selected worst tail.", "Downside/tail risk matters.", "Too little tail data or unstable loss model.", scalar=True),
        _contract(AdvancedLens.ENTROPIC_RISK, (UncertaintyAxis.TAIL, UncertaintyAxis.DECISION), 1960, MetricOrientation.LOWER_BETTER, "Exponential utility/risk transform.", "Risk-sensitive sequential control.", "Risk parameter/utility scale is unjustified.", scalar=True),
        _contract(AdvancedLens.MINIMAX_REGRET, (UncertaintyAxis.ADVERSARIAL, UncertaintyAxis.EPISTEMIC, UncertaintyAxis.DECISION), 1950, MetricOrientation.LOWER_BETTER, "Worst regret across plausible models/worlds.", "Model ambiguity is substantial.", "Plausible model set contains unrealistic extremes.", scalar=True),
        _contract(AdvancedLens.DISTRIBUTIONAL_ROBUSTNESS, (UncertaintyAxis.DISTRIBUTION_SHIFT, UncertaintyAxis.ADVERSARIAL), 2010, MetricOrientation.LOWER_BETTER, "Worst-case performance over a distributional ambiguity set.", "Deployment distribution may shift.", "Ambiguity set/radius lacks empirical justification.", scalar=True),
        _contract(AdvancedLens.VALUE_OF_INFORMATION, (UncertaintyAxis.DECISION, UncertaintyAxis.EPISTEMIC), 1960, MetricOrientation.HIGHER_BETTER, "Expected utility improvement from acquiring information.", "Deciding whether to search/measure/reason more.", "Information cannot change available decisions.", scalar=True),
        _contract(AdvancedLens.INFORMATION_GAIN, (UncertaintyAxis.EPISTEMIC,), 1950, MetricOrientation.HIGHER_BETTER, "Expected reduction in posterior uncertainty.", "Experiment/question selection.", "Novelty is irrelevant to the decision."),
        _contract(AdvancedLens.INFORMATION_DIRECTED, (UncertaintyAxis.EPISTEMIC, UncertaintyAxis.DECISION), 2014, MetricOrientation.LOWER_BETTER, "Trade squared expected regret against information gain.", "Exploration should be tied to decision regret.", "Regret/information estimates are not commensurate."),
        _contract(AdvancedLens.BAYESIAN_MODEL_AVERAGING, (UncertaintyAxis.EPISTEMIC, UncertaintyAxis.PARAMETER), 1990, MetricOrientation.DIAGNOSTIC, "Predictions averaged over posterior model uncertainty.", "Several models remain plausible.", "Posterior model set omits critical alternatives."),
        _contract(AdvancedLens.PAC_BAYES_COMPLEXITY, (UncertaintyAxis.PARAMETER,), 1990, MetricOrientation.LOWER_BETTER, "Generalization-complexity diagnostic from posterior-vs-prior divergence.", "A PAC-Bayes bound is mathematically applicable.", "Used as empirical probability of correctness.", tags=("bound",)),
        _contract(AdvancedLens.OOD_SCORE, (UncertaintyAxis.DISTRIBUTION_SHIFT,), 2018, MetricOrientation.LOWER_BETTER, "Degree to which an input departs from the calibration/training domain.", "Coverage/calibration may fail out of domain.", "OOD score itself is uncalibrated."),
        _contract(AdvancedLens.DRIFT_SCORE, (UncertaintyAxis.TEMPORAL_DRIFT,), 2000, MetricOrientation.LOWER_BETTER, "Change in feature/outcome distributions over time.", "Deployment is nonstationary.", "Seasonality/regime structure is ignored."),
        _contract(AdvancedLens.IDENTIFICATION_GAP, (UncertaintyAxis.CAUSAL_IDENTIFICATION,), 1995, MetricOrientation.LOWER_BETTER, "Residual uncertainty caused by non-identification rather than sampling noise.", "Causal/counterfactual claims are attempted.", "Identification assumptions are hidden or untestable."),
        _contract(AdvancedLens.MEMORY_RECALL_RISK, (UncertaintyAxis.RETRIEVAL,), 1885, MetricOrientation.LOWER_BETTER, "Risk that a useful memory cannot be reliably recalled under current cues.", "Memory-game/index-card routing.", "Ease of recall is misread as truth."),
        _contract(AdvancedLens.GAME_MONTE_CARLO_ERROR, (UncertaintyAxis.ALEATORIC, UncertaintyAxis.EPISTEMIC), 1949, MetricOrientation.LOWER_BETTER, "Finite-simulation error for game/chance estimates.", "Exact combinatorics are infeasible but a simulator is available.", "Simulator differs materially from the real mechanism."),
    )
