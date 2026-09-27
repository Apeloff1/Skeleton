"""Governed feedback-to-production promotion pipeline.

Feedback collection, experiment assignment, evaluation, promotion, and rollback
are separate phases. Recording feedback can never mutate the active production
variant. A candidate may become active only through an evaluation receipt that
is bound to the exact experiment evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Any, Callable

from skeleton.intelligence.experiment_tracker import ExperimentTracker


class FeedbackPromotionError(RuntimeError):
    """Feedback promotion contract was violated."""


def _canonical_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class FeedbackPolicy:
    allowed_data_uses: tuple[str, ...] = ("product_improvement",)
    require_consent: bool = True
    minimum_samples_per_variant: int = 10
    minimum_effect_delta: float = 0.0
    significance_level: float = 0.05

    def __post_init__(self) -> None:
        if not self.allowed_data_uses:
            raise ValueError("allowed_data_uses must not be empty")
        if any(not item or len(item) > 128 for item in self.allowed_data_uses):
            raise ValueError("allowed_data_uses contains an invalid value")
        if self.minimum_samples_per_variant < 2:
            raise ValueError("minimum_samples_per_variant must be at least 2")
        if not math.isfinite(self.minimum_effect_delta):
            raise ValueError("minimum_effect_delta must be finite")
        if not 0.0 < self.significance_level < 1.0:
            raise ValueError("significance_level must be in (0, 1)")


@dataclass(frozen=True, slots=True)
class FeedbackEvent:
    event_id: str
    experiment_id: str
    subject_id: str
    variant: str
    metric: str
    value: float
    consent: bool
    data_use: str
    created_at: float

    def __post_init__(self) -> None:
        for label, value in (
            ("event_id", self.event_id),
            ("experiment_id", self.experiment_id),
            ("subject_id", self.subject_id),
            ("variant", self.variant),
            ("metric", self.metric),
            ("data_use", self.data_use),
        ):
            if not isinstance(value, str) or not value or len(value) > 256:
                raise ValueError(f"invalid {label}")
        if isinstance(self.value, bool) or not math.isfinite(float(self.value)):
            raise ValueError("feedback value must be finite")
        if not math.isfinite(float(self.created_at)) or self.created_at < 0:
            raise ValueError("created_at must be finite and non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "experiment_id": self.experiment_id,
            "subject_id": self.subject_id,
            "variant": self.variant,
            "metric": self.metric,
            "value": float(self.value),
            "consent": bool(self.consent),
            "data_use": self.data_use,
            "created_at": float(self.created_at),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class PromotionEvaluationReceipt:
    experiment_id: str
    baseline_variant: str
    candidate_variant: str
    baseline_samples: int
    candidate_samples: int
    baseline_mean: float
    candidate_mean: float
    effect_delta: float
    p_value: float | None
    significant: bool
    eligible: bool
    evaluator: str
    evidence_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "baseline_variant": self.baseline_variant,
            "candidate_variant": self.candidate_variant,
            "baseline_samples": self.baseline_samples,
            "candidate_samples": self.candidate_samples,
            "baseline_mean": self.baseline_mean,
            "candidate_mean": self.candidate_mean,
            "effect_delta": self.effect_delta,
            "p_value": self.p_value,
            "significant": self.significant,
            "eligible": self.eligible,
            "evaluator": self.evaluator,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True, slots=True)
class PromotionActionReceipt:
    experiment_id: str
    action: str
    from_variant: str
    to_variant: str
    evaluation_digest: str
    reason: str
    occurred_at: float

    def __post_init__(self) -> None:
        if self.action not in {"promoted", "rolled_back"}:
            raise ValueError("unsupported promotion action")
        if not self.reason or len(self.reason) > 512:
            raise ValueError("promotion action requires a bounded reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "action": self.action,
            "from_variant": self.from_variant,
            "to_variant": self.to_variant,
            "evaluation_digest": self.evaluation_digest,
            "reason": self.reason,
            "occurred_at": self.occurred_at,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_dict())


class FeedbackPromotionPipeline:
    """Separate experiment evidence from production behavior mutation."""

    evaluator_version = "feedback-promotion-v1"

    def __init__(
        self,
        policy: FeedbackPolicy | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or FeedbackPolicy()
        self.tracker = ExperimentTracker(
            significance_level=self.policy.significance_level
        )
        self._clock = clock
        self._baseline: dict[str, str] = {}
        self._active: dict[str, str] = {}
        self._assignments: dict[tuple[str, str], str] = {}
        self._events: dict[str, FeedbackEvent] = {}
        self._evaluations: dict[str, PromotionEvaluationReceipt] = {}
        self._history: list[PromotionActionReceipt] = []

    def create_experiment(
        self,
        experiment_id: str,
        *,
        baseline_variant: str = "baseline",
        candidate_variant: str = "candidate",
        baseline_weight: int = 50,
        candidate_weight: int = 50,
    ) -> None:
        if experiment_id in self._baseline:
            raise FeedbackPromotionError("experiment already exists")
        if baseline_variant == candidate_variant:
            raise ValueError("baseline and candidate variants must differ")
        self.tracker.create(
            experiment_id,
            variants=[baseline_variant, candidate_variant],
            weights=[baseline_weight, candidate_weight],
        )
        self._baseline[experiment_id] = baseline_variant
        self._active[experiment_id] = baseline_variant

    def assign(self, experiment_id: str, subject_id: str) -> str:
        key = (experiment_id, subject_id)
        existing = self._assignments.get(key)
        if existing is not None:
            return existing
        assigned = self.tracker.assign(experiment_id, subject_id)
        if assigned is None:
            raise FeedbackPromotionError("experiment assignment is unavailable")
        self._assignments[key] = assigned
        return assigned

    def active_variant(self, experiment_id: str) -> str:
        try:
            return self._active[experiment_id]
        except KeyError as exc:
            raise FeedbackPromotionError("unknown experiment") from exc

    def record_feedback(self, event: FeedbackEvent) -> FeedbackEvent:
        if event.experiment_id not in self._baseline:
            raise FeedbackPromotionError("unknown experiment")
        if self.policy.require_consent and not event.consent:
            raise FeedbackPromotionError("feedback consent is required")
        if event.data_use not in self.policy.allowed_data_uses:
            raise FeedbackPromotionError("feedback data use is not permitted")

        assigned = self.assign(event.experiment_id, event.subject_id)
        if event.variant != assigned:
            raise FeedbackPromotionError(
                "feedback variant does not match deterministic assignment"
            )

        prior = self._events.get(event.event_id)
        if prior is not None:
            if prior.digest != event.digest:
                raise FeedbackPromotionError("feedback event id conflict")
            return prior

        self.tracker.record(
            event.experiment_id,
            event.variant,
            event.value,
        )
        self._events[event.event_id] = event
        return event

    def evaluate(
        self,
        experiment_id: str,
        *,
        candidate_variant: str,
    ) -> PromotionEvaluationReceipt:
        baseline_variant = self.active_baseline(experiment_id)
        experiment = self.tracker._experiments.get(experiment_id)
        if experiment is None:
            raise FeedbackPromotionError("unknown experiment")
        if candidate_variant == baseline_variant:
            raise FeedbackPromotionError("candidate must differ from baseline")
        if candidate_variant not in experiment.variants:
            raise FeedbackPromotionError("unknown candidate variant")

        baseline = experiment.variants[baseline_variant]
        candidate = experiment.variants[candidate_variant]
        baseline_mean = baseline.mean()
        candidate_mean = candidate.mean()
        if baseline_mean is None or candidate_mean is None:
            raise FeedbackPromotionError("experiment has no evaluation outcomes")

        significance = self.tracker.significance(experiment_id)
        p_value = significance.get("p_value")
        significant = bool(significance.get("significant"))
        effect_delta = float(candidate_mean - baseline_mean)
        enough_samples = (
            len(baseline.outcomes) >= self.policy.minimum_samples_per_variant
            and len(candidate.outcomes) >= self.policy.minimum_samples_per_variant
        )
        eligible = (
            enough_samples
            and significant
            and effect_delta > self.policy.minimum_effect_delta
        )
        evidence_payload = {
            "experiment_id": experiment_id,
            "baseline_variant": baseline_variant,
            "candidate_variant": candidate_variant,
            "baseline_outcomes": list(baseline.outcomes),
            "candidate_outcomes": list(candidate.outcomes),
            "policy": {
                "minimum_samples_per_variant": (
                    self.policy.minimum_samples_per_variant
                ),
                "minimum_effect_delta": self.policy.minimum_effect_delta,
                "significance_level": self.policy.significance_level,
            },
        }
        receipt = PromotionEvaluationReceipt(
            experiment_id=experiment_id,
            baseline_variant=baseline_variant,
            candidate_variant=candidate_variant,
            baseline_samples=len(baseline.outcomes),
            candidate_samples=len(candidate.outcomes),
            baseline_mean=float(baseline_mean),
            candidate_mean=float(candidate_mean),
            effect_delta=effect_delta,
            p_value=None if p_value is None else float(p_value),
            significant=significant,
            eligible=eligible,
            evaluator=self.evaluator_version,
            evidence_digest=_canonical_digest(evidence_payload),
        )
        self._evaluations[experiment_id] = receipt
        return receipt

    def active_baseline(self, experiment_id: str) -> str:
        try:
            return self._baseline[experiment_id]
        except KeyError as exc:
            raise FeedbackPromotionError("unknown experiment") from exc

    def promote(
        self,
        experiment_id: str,
        receipt: PromotionEvaluationReceipt,
        *,
        reason: str = "evaluation threshold satisfied",
    ) -> PromotionActionReceipt:
        latest = self._evaluations.get(experiment_id)
        if latest is None:
            raise FeedbackPromotionError(
                "promotion requires an evaluation receipt"
            )
        if not isinstance(receipt, PromotionEvaluationReceipt):
            raise FeedbackPromotionError(
                "promotion requires an evaluation receipt"
            )
        if receipt != latest:
            raise FeedbackPromotionError("evaluation receipt is stale or foreign")
        if not receipt.eligible:
            raise FeedbackPromotionError("evaluation receipt is not eligible")

        current = self.active_variant(experiment_id)
        action = PromotionActionReceipt(
            experiment_id=experiment_id,
            action="promoted",
            from_variant=current,
            to_variant=receipt.candidate_variant,
            evaluation_digest=receipt.evidence_digest,
            reason=reason,
            occurred_at=float(self._clock()),
        )
        self._active[experiment_id] = receipt.candidate_variant
        self._history.append(action)
        return action

    def rollback(
        self,
        experiment_id: str,
        *,
        reason: str,
    ) -> PromotionActionReceipt:
        current = self.active_variant(experiment_id)
        baseline = self.active_baseline(experiment_id)
        latest = self._evaluations.get(experiment_id)
        action = PromotionActionReceipt(
            experiment_id=experiment_id,
            action="rolled_back",
            from_variant=current,
            to_variant=baseline,
            evaluation_digest=(
                "" if latest is None else latest.evidence_digest
            ),
            reason=reason,
            occurred_at=float(self._clock()),
        )
        self._active[experiment_id] = baseline
        self._history.append(action)
        return action

    def promotion_history(
        self,
        experiment_id: str | None = None,
    ) -> tuple[PromotionActionReceipt, ...]:
        if experiment_id is None:
            return tuple(self._history)
        return tuple(
            item
            for item in self._history
            if item.experiment_id == experiment_id
        )


__all__ = [
    "FeedbackEvent",
    "FeedbackPolicy",
    "FeedbackPromotionError",
    "FeedbackPromotionPipeline",
    "PromotionActionReceipt",
    "PromotionEvaluationReceipt",
]
