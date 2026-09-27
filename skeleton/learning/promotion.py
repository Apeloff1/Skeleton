"""Controlled feedback-to-production promotion.

Feedback collection is deliberately separate from behavior mutation. Experiment
assignment is deterministic, holdouts are isolated, consent/data-use is
validated at collection, and production promotion requires an external
evaluation receipt. Every promotion is reversible to its declared baseline.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from skeleton.kernel.errors import KernelError


SCHEMA_VERSION = 1
_BUCKETS = 10_000
_MAX_TEXT = 512


class FeedbackPromotionError(KernelError):
    code = "LEARNING.FEEDBACK_PROMOTION"
    http_status = 422


def _text(name: str, value: object, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FeedbackPromotionError(f"{name} must be non-empty text")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise FeedbackPromotionError(f"{name} is not normalized")
    return normalized


def _unit(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FeedbackPromotionError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise FeedbackPromotionError(f"{name} must be between 0 and 1")
    return number


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FeedbackPromotionError(
            f"{name} must be a non-negative integer"
        )
    return value


def _positive_int(name: str, value: object) -> int:
    result = _non_negative_int(name, value)
    if result == 0:
        raise FeedbackPromotionError(f"{name} must be positive")
    return result


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise FeedbackPromotionError(
            "feedback promotion evidence must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    experiment_id: str
    baseline_version: str
    candidate_version: str
    assignment_salt: str
    data_use_purpose: str
    holdout_bps: int = 1000
    candidate_bps: int = 4500
    min_variant_samples: int = 25

    def __post_init__(self) -> None:
        for name in (
            "experiment_id",
            "baseline_version",
            "candidate_version",
            "assignment_salt",
            "data_use_purpose",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if self.baseline_version == self.candidate_version:
            raise FeedbackPromotionError(
                "candidate_version must differ from baseline_version"
            )
        holdout = _non_negative_int("holdout_bps", self.holdout_bps)
        candidate = _positive_int("candidate_bps", self.candidate_bps)
        if holdout >= _BUCKETS:
            raise FeedbackPromotionError("holdout_bps must be below 10000")
        if candidate > _BUCKETS - holdout:
            raise FeedbackPromotionError(
                "candidate_bps exceeds non-holdout population"
            )
        object.__setattr__(
            self,
            "min_variant_samples",
            _positive_int("min_variant_samples", self.min_variant_samples),
        )

    def assignment_for(self, subject_id: str) -> str:
        subject = _text("subject_id", subject_id)
        digest = hashlib.sha256(
            (
                self.experiment_id
                + ":"
                + self.assignment_salt
                + ":"
                + subject
            ).encode("utf-8")
        ).digest()
        bucket = int.from_bytes(digest[:8], "big") % _BUCKETS
        if bucket < self.holdout_bps:
            return "holdout"
        if bucket < self.holdout_bps + self.candidate_bps:
            return "candidate"
        return "baseline"

    @property
    def digest(self) -> str:
        return _digest(
            {
                "experiment_id": self.experiment_id,
                "baseline_version": self.baseline_version,
                "candidate_version": self.candidate_version,
                "assignment_salt": self.assignment_salt,
                "data_use_purpose": self.data_use_purpose,
                "holdout_bps": self.holdout_bps,
                "candidate_bps": self.candidate_bps,
                "min_variant_samples": self.min_variant_samples,
            }
        )


@dataclass(frozen=True, slots=True)
class ExperimentAssignment:
    experiment_id: str
    subject_id: str
    variant: str
    spec_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "experiment_id",
            _text("experiment_id", self.experiment_id),
        )
        object.__setattr__(self, "subject_id", _text("subject_id", self.subject_id))
        if self.variant not in {"baseline", "candidate", "holdout"}:
            raise FeedbackPromotionError("variant is invalid")
        if len(self.spec_digest) != 64:
            raise FeedbackPromotionError("spec_digest must be sha256")


@dataclass(frozen=True, slots=True)
class FeedbackEvent:
    event_id: str
    experiment_id: str
    subject_id: str
    variant: str
    score: float
    observed_at: int
    consent: bool
    data_use_purpose: str
    spec_digest: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("event_id", "experiment_id", "subject_id", "data_use_purpose"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if self.variant not in {"baseline", "candidate", "holdout"}:
            raise FeedbackPromotionError("feedback variant is invalid")
        object.__setattr__(self, "score", _unit("score", self.score))
        object.__setattr__(
            self,
            "observed_at",
            _non_negative_int("observed_at", self.observed_at),
        )
        if not isinstance(self.consent, bool):
            raise FeedbackPromotionError("consent must be boolean")
        if not self.consent:
            raise FeedbackPromotionError(
                "feedback cannot be retained without explicit consent"
            )
        if len(self.spec_digest) != 64:
            raise FeedbackPromotionError("spec_digest must be sha256")
        if self.schema_version != SCHEMA_VERSION:
            raise FeedbackPromotionError("unsupported feedback schema")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "experiment_id": self.experiment_id,
            "subject_id": self.subject_id,
            "variant": self.variant,
            "score": self.score,
            "observed_at": self.observed_at,
            "consent": self.consent,
            "data_use_purpose": self.data_use_purpose,
            "spec_digest": self.spec_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


class FeedbackLedger:
    """Collection-only feedback ledger. It has no production mutation method."""

    def __init__(self) -> None:
        self._events: dict[str, FeedbackEvent] = {}

    def assign(
        self,
        spec: ExperimentSpec,
        subject_id: str,
    ) -> ExperimentAssignment:
        subject = _text("subject_id", subject_id)
        return ExperimentAssignment(
            experiment_id=spec.experiment_id,
            subject_id=subject,
            variant=spec.assignment_for(subject),
            spec_digest=spec.digest,
        )

    def collect(
        self,
        spec: ExperimentSpec,
        assignment: ExperimentAssignment,
        *,
        event_id: str,
        score: float,
        observed_at: int,
        consent: bool,
        data_use_purpose: str,
    ) -> FeedbackEvent:
        if assignment.experiment_id != spec.experiment_id:
            raise FeedbackPromotionError("assignment belongs to another experiment")
        if assignment.spec_digest != spec.digest:
            raise FeedbackPromotionError("assignment spec digest is stale")
        expected = spec.assignment_for(assignment.subject_id)
        if assignment.variant != expected:
            raise FeedbackPromotionError("assignment variant was tampered")
        if data_use_purpose != spec.data_use_purpose:
            raise FeedbackPromotionError("feedback data-use purpose is not allowed")

        event = FeedbackEvent(
            event_id=event_id,
            experiment_id=spec.experiment_id,
            subject_id=assignment.subject_id,
            variant=assignment.variant,
            score=score,
            observed_at=observed_at,
            consent=consent,
            data_use_purpose=data_use_purpose,
            spec_digest=spec.digest,
        )
        prior = self._events.get(event.event_id)
        if prior is not None:
            if prior != event:
                raise FeedbackPromotionError(
                    "feedback event id was reused with different content"
                )
            return prior
        self._events[event.event_id] = event
        return event

    def events(self, experiment_id: str) -> tuple[FeedbackEvent, ...]:
        experiment = _text("experiment_id", experiment_id)
        return tuple(
            sorted(
                (
                    event
                    for event in self._events.values()
                    if event.experiment_id == experiment
                ),
                key=lambda event: (event.observed_at, event.event_id),
            )
        )


@dataclass(frozen=True, slots=True)
class EvaluationReceipt:
    experiment_id: str
    baseline_version: str
    candidate_version: str
    evaluator_id: str
    passed: bool
    event_ids: tuple[str, ...]
    metric_delta: float
    evaluated_at: int
    evidence_ref: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "experiment_id",
            "baseline_version",
            "candidate_version",
            "evaluator_id",
            "evidence_ref",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if not isinstance(self.passed, bool):
            raise FeedbackPromotionError("passed must be boolean")
        if not self.event_ids:
            raise FeedbackPromotionError("evaluation receipt needs event ids")
        normalized_ids = tuple(_text("event_id", item) for item in self.event_ids)
        if len(set(normalized_ids)) != len(normalized_ids):
            raise FeedbackPromotionError("evaluation event ids contain duplicates")
        object.__setattr__(self, "event_ids", normalized_ids)
        if isinstance(self.metric_delta, bool) or not isinstance(
            self.metric_delta,
            (int, float),
        ):
            raise FeedbackPromotionError("metric_delta must be numeric")
        metric = float(self.metric_delta)
        if not math.isfinite(metric):
            raise FeedbackPromotionError("metric_delta must be finite")
        object.__setattr__(self, "metric_delta", metric)
        object.__setattr__(
            self,
            "evaluated_at",
            _non_negative_int("evaluated_at", self.evaluated_at),
        )
        if self.schema_version != SCHEMA_VERSION:
            raise FeedbackPromotionError("unsupported evaluation receipt schema")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "baseline_version": self.baseline_version,
            "candidate_version": self.candidate_version,
            "evaluator_id": self.evaluator_id,
            "passed": self.passed,
            "event_ids": list(self.event_ids),
            "metric_delta": self.metric_delta,
            "evaluated_at": self.evaluated_at,
            "evidence_ref": self.evidence_ref,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class PromotionReceipt:
    experiment_id: str
    from_version: str
    to_version: str
    evaluation_digest: str
    promoted_at: int
    rollback: bool = False
    reason: str = ""
    schema_version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "evaluation_digest": self.evaluation_digest,
            "promoted_at": self.promoted_at,
            "rollback": self.rollback,
            "reason": self.reason,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


class FeedbackPromotionPipeline:
    """Controlled evaluation -> promotion -> rollback state machine."""

    def __init__(self) -> None:
        self._active: dict[str, str] = {}
        self._receipts: dict[str, list[PromotionReceipt]] = {}

    def active_version(self, spec: ExperimentSpec) -> str:
        return self._active.get(spec.experiment_id, spec.baseline_version)

    def promote(
        self,
        spec: ExperimentSpec,
        events: Sequence[FeedbackEvent],
        receipt: EvaluationReceipt,
        *,
        promoted_at: int,
    ) -> PromotionReceipt:
        if receipt.experiment_id != spec.experiment_id:
            raise FeedbackPromotionError("evaluation belongs to another experiment")
        if (
            receipt.baseline_version != spec.baseline_version
            or receipt.candidate_version != spec.candidate_version
        ):
            raise FeedbackPromotionError("evaluation versions do not match experiment")
        if not receipt.passed:
            raise FeedbackPromotionError("promotion requires passing evaluation")
        if receipt.metric_delta <= 0.0:
            raise FeedbackPromotionError(
                "promotion requires positive evaluated improvement"
            )

        by_id = {event.event_id: event for event in events}
        selected: list[FeedbackEvent] = []
        for event_id in receipt.event_ids:
            event = by_id.get(event_id)
            if event is None:
                raise FeedbackPromotionError(
                    "evaluation references unavailable feedback"
                )
            if event.experiment_id != spec.experiment_id:
                raise FeedbackPromotionError(
                    "evaluation references another experiment"
                )
            if event.spec_digest != spec.digest:
                raise FeedbackPromotionError(
                    "evaluation references stale experiment assignment"
                )
            if event.variant == "holdout":
                raise FeedbackPromotionError(
                    "holdout feedback cannot enter promotion evaluation"
                )
            if event.data_use_purpose != spec.data_use_purpose or not event.consent:
                raise FeedbackPromotionError(
                    "evaluation references disallowed feedback data"
                )
            if spec.assignment_for(event.subject_id) != event.variant:
                raise FeedbackPromotionError(
                    "evaluation contains assignment leakage"
                )
            selected.append(event)

        counts = {
            "baseline": sum(event.variant == "baseline" for event in selected),
            "candidate": sum(event.variant == "candidate" for event in selected),
        }
        if min(counts.values()) < spec.min_variant_samples:
            raise FeedbackPromotionError(
                "evaluation does not meet minimum variant sample count"
            )

        current = self.active_version(spec)
        if current not in {spec.baseline_version, spec.candidate_version}:
            raise FeedbackPromotionError("active version is outside experiment")
        if current == spec.candidate_version:
            prior = self._receipts.get(spec.experiment_id, [])
            if prior and prior[-1].evaluation_digest == receipt.digest:
                return prior[-1]
            raise FeedbackPromotionError(
                "candidate is already active under different evaluation"
            )

        result = PromotionReceipt(
            experiment_id=spec.experiment_id,
            from_version=spec.baseline_version,
            to_version=spec.candidate_version,
            evaluation_digest=receipt.digest,
            promoted_at=_non_negative_int("promoted_at", promoted_at),
        )
        self._active[spec.experiment_id] = spec.candidate_version
        self._receipts.setdefault(spec.experiment_id, []).append(result)
        return result

    def rollback(
        self,
        spec: ExperimentSpec,
        *,
        reason: str,
        rolled_back_at: int,
    ) -> PromotionReceipt:
        if self.active_version(spec) != spec.candidate_version:
            raise FeedbackPromotionError("candidate version is not active")
        history = self._receipts.get(spec.experiment_id, [])
        if not history:
            raise FeedbackPromotionError("promotion receipt is unavailable")
        result = PromotionReceipt(
            experiment_id=spec.experiment_id,
            from_version=spec.candidate_version,
            to_version=spec.baseline_version,
            evaluation_digest=history[-1].evaluation_digest,
            promoted_at=_non_negative_int("rolled_back_at", rolled_back_at),
            rollback=True,
            reason=_text("reason", reason),
        )
        self._active[spec.experiment_id] = spec.baseline_version
        history.append(result)
        return result

    def receipts(self, experiment_id: str) -> tuple[PromotionReceipt, ...]:
        return tuple(self._receipts.get(_text("experiment_id", experiment_id), ()))


__all__ = [
    "EvaluationReceipt",
    "ExperimentAssignment",
    "ExperimentSpec",
    "FeedbackEvent",
    "FeedbackLedger",
    "FeedbackPromotionError",
    "FeedbackPromotionPipeline",
    "PromotionReceipt",
]
