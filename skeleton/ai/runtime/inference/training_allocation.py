"""Adaptive, holdout-safe training-method allocation.

The allocator learns *which training families to spend compute on* from
development/regression/Mirror validation evidence.  Promotion holdouts and
production observations are rejected so the allocation loop cannot optimize
against the final promotion oracle.

Allocation is deterministic: observed validation gain per compute unit is
shrinkage-weighted by evidence count, methods with no evidence receive one
exploration repeat, negative non-mandatory methods can be omitted, and hard
repeat/total-repeat caps bound amplification.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable, Sequence

from .training_methods import MethodWeight, TrainingMethod


_ALLOWED_FEEDBACK_CLASSES = frozenset({
    "development",
    "regression",
    "mirror_validation",
})


class TrainingAllocationError(RuntimeError):
    """Training-method allocation evidence or policy is invalid."""


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TrainingAllocationError(
            "allocation state is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _finite(
    value: object,
    name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TrainingAllocationError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise TrainingAllocationError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise TrainingAllocationError(f"{name} is below minimum")
    if maximum is not None and result > maximum:
        raise TrainingAllocationError(f"{name} exceeds maximum")
    return result


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TrainingAllocationError(f"{name} must be sha256 text")
    result = value.strip().lower()
    if (
        len(result) != 64
        or any(ch not in "0123456789abcdef" for ch in result)
    ):
        raise TrainingAllocationError(f"{name} must be lowercase sha256")
    return result


@dataclass(frozen=True, slots=True)
class MethodValidationObservation:
    """One method-level validation result from a non-promotion dataset."""

    method: TrainingMethod
    evaluation_class: str
    validation_gain: float
    compute_units: float
    evaluation_digest: str
    plan_digest: str
    sample_count: int = 1

    def __post_init__(self) -> None:
        try:
            method = TrainingMethod(self.method)
        except ValueError as exc:
            raise TrainingAllocationError(
                "observation uses unsupported training method"
            ) from exc
        object.__setattr__(self, "method", method)
        if self.evaluation_class not in _ALLOWED_FEEDBACK_CLASSES:
            raise TrainingAllocationError(
                "adaptive allocation may use only development, regression "
                "or Mirror validation evidence"
            )
        object.__setattr__(
            self,
            "validation_gain",
            _finite(
                self.validation_gain,
                "validation_gain",
                minimum=-1_000_000.0,
                maximum=1_000_000.0,
            ),
        )
        units = _finite(
            self.compute_units,
            "compute_units",
            minimum=1e-12,
            maximum=1_000_000_000.0,
        )
        object.__setattr__(self, "compute_units", units)
        object.__setattr__(
            self,
            "evaluation_digest",
            _sha(self.evaluation_digest, "evaluation_digest"),
        )
        object.__setattr__(
            self,
            "plan_digest",
            _sha(self.plan_digest, "plan_digest"),
        )
        if (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, int)
            or not 1 <= self.sample_count <= 1_000_000
        ):
            raise TrainingAllocationError(
                "sample_count must be in [1, 1000000]"
            )

    @property
    def efficiency(self) -> float:
        return self.validation_gain / self.compute_units

    @property
    def digest(self) -> str:
        return _digest(
            {
                "method": self.method.value,
                "evaluation_class": self.evaluation_class,
                "validation_gain": self.validation_gain,
                "compute_units": self.compute_units,
                "evaluation_digest": self.evaluation_digest,
                "plan_digest": self.plan_digest,
                "sample_count": self.sample_count,
            }
        )


@dataclass(frozen=True, slots=True)
class TrainingAllocationPolicy:
    """Compute-allocation policy for the next training candidate."""

    max_repeat_per_method: int = 4
    max_total_repeats: int = 24
    exploration_repeat: int = 1
    shrinkage_samples: float = 4.0
    mandatory_methods: tuple[TrainingMethod, ...] = (
        TrainingMethod.SUPERVISED_INSTRUCTION,
        TrainingMethod.CAUSAL_LANGUAGE_MODELING,
        TrainingMethod.SELF_SUPERVISED_SPAN,
    )

    def __post_init__(self) -> None:
        for name, value, lower, upper in (
            ("max_repeat_per_method", self.max_repeat_per_method, 1, 16),
            ("max_total_repeats", self.max_total_repeats, 1, 256),
            ("exploration_repeat", self.exploration_repeat, 1, 16),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not lower <= value <= upper
            ):
                raise TrainingAllocationError(
                    f"{name} must be in [{lower}, {upper}]"
                )
        if self.exploration_repeat > self.max_repeat_per_method:
            raise TrainingAllocationError(
                "exploration_repeat exceeds per-method cap"
            )
        object.__setattr__(
            self,
            "shrinkage_samples",
            _finite(
                self.shrinkage_samples,
                "shrinkage_samples",
                minimum=0.0,
                maximum=1_000_000.0,
            ),
        )
        methods: list[TrainingMethod] = []
        for raw in self.mandatory_methods:
            try:
                method = TrainingMethod(raw)
            except ValueError as exc:
                raise TrainingAllocationError(
                    "mandatory method is unsupported"
                ) from exc
            if method not in methods:
                methods.append(method)
        object.__setattr__(self, "mandatory_methods", tuple(methods))
        minimum_total = len(methods)
        if minimum_total > self.max_total_repeats:
            raise TrainingAllocationError(
                "max_total_repeats cannot fit mandatory methods"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "max_repeat_per_method": self.max_repeat_per_method,
                "max_total_repeats": self.max_total_repeats,
                "exploration_repeat": self.exploration_repeat,
                "shrinkage_samples": self.shrinkage_samples,
                "mandatory_methods": [
                    item.value for item in self.mandatory_methods
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class MethodAllocationScore:
    method: TrainingMethod
    observations: int
    sample_count: int
    mean_gain: float
    mean_compute_units: float
    mean_efficiency: float
    shrunk_efficiency: float
    repeat: int
    included: bool

    @property
    def digest(self) -> str:
        return _digest(
            {
                "method": self.method.value,
                "observations": self.observations,
                "sample_count": self.sample_count,
                "mean_gain": self.mean_gain,
                "mean_compute_units": self.mean_compute_units,
                "mean_efficiency": self.mean_efficiency,
                "shrunk_efficiency": self.shrunk_efficiency,
                "repeat": self.repeat,
                "included": self.included,
            }
        )


@dataclass(frozen=True, slots=True)
class AdaptiveMethodAllocation:
    """Deterministic method weights for one subsequent training plan."""

    policy_digest: str
    observation_digests: tuple[str, ...]
    scores: tuple[MethodAllocationScore, ...]
    method_weights: tuple[MethodWeight, ...]
    allocation_digest: str

    def __post_init__(self) -> None:
        if not self.method_weights:
            raise TrainingAllocationError(
                "allocation must include at least one method"
            )
        if sum(item.repeat for item in self.method_weights) < 1:
            raise TrainingAllocationError(
                "allocation must consume positive training repeats"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.adaptive_method_allocation.v1",
            "policy_digest": self.policy_digest,
            "observation_digests": list(self.observation_digests),
            "scores": [
                {
                    "method": score.method.value,
                    "observations": score.observations,
                    "sample_count": score.sample_count,
                    "mean_gain": score.mean_gain,
                    "mean_compute_units": score.mean_compute_units,
                    "mean_efficiency": score.mean_efficiency,
                    "shrunk_efficiency": score.shrunk_efficiency,
                    "repeat": score.repeat,
                    "included": score.included,
                    "score_digest": score.digest,
                }
                for score in self.scores
            ],
            "method_weights": [
                {"method": item.method.value, "repeat": item.repeat}
                for item in self.method_weights
            ],
            "allocation_digest": self.allocation_digest,
        }


def allocate_training_methods(
    observations: Sequence[MethodValidationObservation],
    *,
    available_methods: Iterable[TrainingMethod] = tuple(TrainingMethod),
    policy: TrainingAllocationPolicy | None = None,
) -> AdaptiveMethodAllocation:
    """Allocate next-candidate repeats from validation gain per compute unit."""

    actual = policy or TrainingAllocationPolicy()
    available: list[TrainingMethod] = []
    for raw in available_methods:
        try:
            method = TrainingMethod(raw)
        except ValueError as exc:
            raise TrainingAllocationError(
                "available method is unsupported"
            ) from exc
        if method not in available:
            available.append(method)
    if not available:
        raise TrainingAllocationError("available_methods must be non-empty")
    missing_mandatory = set(actual.mandatory_methods) - set(available)
    if missing_mandatory:
        raise TrainingAllocationError(
            "available methods omit a mandatory method"
        )

    rows = tuple(observations)
    if any(
        not isinstance(item, MethodValidationObservation)
        for item in rows
    ):
        raise TypeError(
            "observations must contain MethodValidationObservation values"
        )
    observation_digests = tuple(sorted(item.digest for item in rows))

    by_method: dict[TrainingMethod, list[MethodValidationObservation]] = {
        method: [] for method in available
    }
    for item in rows:
        if item.method in by_method:
            by_method[item.method].append(item)

    raw_rows: list[
        tuple[TrainingMethod, int, int, float, float, float, float]
    ] = []
    positive_efficiencies: list[float] = []
    for method in available:
        history = by_method[method]
        count = len(history)
        samples = sum(item.sample_count for item in history)
        if history:
            weighted_gain = sum(
                item.validation_gain * item.sample_count
                for item in history
            )
            weighted_compute = sum(
                item.compute_units * item.sample_count
                for item in history
            )
            mean_gain = weighted_gain / samples
            mean_compute = weighted_compute / samples
            mean_efficiency = weighted_gain / max(
                weighted_compute,
                1e-12,
            )
            shrink = samples / (
                samples + actual.shrinkage_samples
            )
            shrunk = mean_efficiency * shrink
            if shrunk > 0.0:
                positive_efficiencies.append(shrunk)
        else:
            mean_gain = 0.0
            mean_compute = 0.0
            mean_efficiency = 0.0
            shrunk = 0.0
        raw_rows.append(
            (
                method,
                count,
                samples,
                mean_gain,
                mean_compute,
                mean_efficiency,
                shrunk,
            )
        )

    best_positive = max(positive_efficiencies, default=0.0)
    scored: list[MethodAllocationScore] = []
    tentative: dict[TrainingMethod, int] = {}

    for (
        method,
        count,
        samples,
        mean_gain,
        mean_compute,
        mean_efficiency,
        shrunk,
    ) in raw_rows:
        mandatory = method in actual.mandatory_methods
        if count == 0:
            repeat = actual.exploration_repeat
            included = True
        elif shrunk <= 0.0 and not mandatory:
            repeat = 0
            included = False
        elif best_positive <= 0.0:
            repeat = 1
            included = True
        else:
            relative = max(0.0, shrunk) / best_positive
            repeat = 1 + int(
                round(
                    relative
                    * (actual.max_repeat_per_method - 1)
                )
            )
            repeat = min(actual.max_repeat_per_method, max(1, repeat))
            included = True

        if mandatory and repeat == 0:
            repeat = 1
            included = True
        tentative[method] = repeat
        scored.append(
            MethodAllocationScore(
                method=method,
                observations=count,
                sample_count=samples,
                mean_gain=mean_gain,
                mean_compute_units=mean_compute,
                mean_efficiency=mean_efficiency,
                shrunk_efficiency=shrunk,
                repeat=repeat,
                included=included,
            )
        )

    total = sum(tentative.values())
    if total > actual.max_total_repeats:
        # Remove repeats from the least efficient, non-mandatory methods first.
        ranked = sorted(
            scored,
            key=lambda item: (
                item.method in actual.mandatory_methods,
                item.shrunk_efficiency,
                item.sample_count,
                item.method.value,
            ),
        )
        while total > actual.max_total_repeats:
            changed = False
            for score in ranked:
                method = score.method
                minimum = 1 if method in actual.mandatory_methods else 0
                if tentative[method] > minimum:
                    tentative[method] -= 1
                    total -= 1
                    changed = True
                    if total <= actual.max_total_repeats:
                        break
            if not changed:
                raise TrainingAllocationError(
                    "allocation budget cannot satisfy mandatory method floor"
                )

    final_scores = tuple(
        MethodAllocationScore(
            method=item.method,
            observations=item.observations,
            sample_count=item.sample_count,
            mean_gain=item.mean_gain,
            mean_compute_units=item.mean_compute_units,
            mean_efficiency=item.mean_efficiency,
            shrunk_efficiency=item.shrunk_efficiency,
            repeat=tentative[item.method],
            included=tentative[item.method] > 0,
        )
        for item in sorted(scored, key=lambda row: row.method.value)
    )
    weights = tuple(
        MethodWeight(score.method, score.repeat)
        for score in final_scores
        if score.repeat > 0
    )
    payload = {
        "schema_version": "skeleton.adaptive_method_allocation.v1",
        "policy_digest": actual.digest,
        "observation_digests": list(observation_digests),
        "scores": [score.digest for score in final_scores],
        "method_weights": [
            {"method": item.method.value, "repeat": item.repeat}
            for item in weights
        ],
    }
    return AdaptiveMethodAllocation(
        policy_digest=actual.digest,
        observation_digests=observation_digests,
        scores=final_scores,
        method_weights=weights,
        allocation_digest=_digest(payload),
    )


__all__ = [
    "AdaptiveMethodAllocation",
    "MethodAllocationScore",
    "MethodValidationObservation",
    "TrainingAllocationError",
    "TrainingAllocationPolicy",
    "allocate_training_methods",
]
