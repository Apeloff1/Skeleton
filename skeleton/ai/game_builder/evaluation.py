"""Independent evaluator-ensemble primitives for the AI game-builder forge.

The creative rivals never become promotion authority.  This module provides a
small deterministic aggregation layer around independent evaluators so one
judge, one ordering, or one confidence score cannot silently become project
truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, Mapping

from .contracts import QUALITY_AXES, Rival, canonical_digest, normalize_quality


class EvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    evaluator_id: str
    candidate_digest: str
    quality: tuple[tuple[str, float], ...]
    confidence: float
    evidence_digest: str
    method_id: str

    @classmethod
    def create(
        cls,
        *,
        evaluator_id: str,
        candidate_digest: str,
        quality: Mapping[str, float],
        confidence: float,
        evidence_digest: str,
        method_id: str,
    ) -> "JudgeVerdict":
        evaluator_id = evaluator_id.strip()
        method_id = method_id.strip()
        if not evaluator_id or evaluator_id in {Rival.A.value, Rival.B.value}:
            raise ValueError("evaluator must be independent from both rivals")
        if not method_id:
            raise ValueError("method_id must be non-empty")
        if len(candidate_digest) < 16 or len(evidence_digest) < 16:
            raise ValueError("candidate/evidence identities must be stable digests")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError("confidence must be numeric")
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be within [0,1]")
        return cls(
            evaluator_id=evaluator_id,
            candidate_digest=candidate_digest,
            quality=normalize_quality(quality),
            confidence=confidence,
            evidence_digest=evidence_digest,
            method_id=method_id,
        )

    @property
    def quality_map(self) -> dict[str, float]:
        return dict(self.quality)

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "candidate_digest": self.candidate_digest,
                "confidence": self.confidence,
                "evaluator_id": self.evaluator_id,
                "evidence_digest": self.evidence_digest,
                "method_id": self.method_id,
                "quality": dict(self.quality),
            }
        )


@dataclass(frozen=True, slots=True)
class PanelDecision:
    candidate_digest: str
    evaluator_ids: tuple[str, ...]
    method_ids: tuple[str, ...]
    aggregate_quality: tuple[tuple[str, float], ...]
    per_axis_spread: tuple[tuple[str, float], ...]
    median_confidence: float
    minimum_confidence: float
    max_disagreement: float
    disagreement_axes: tuple[str, ...]
    eligible: bool
    requires_appeal: bool
    decision_digest: str

    @property
    def quality_map(self) -> dict[str, float]:
        return dict(self.aggregate_quality)

    @property
    def spread_map(self) -> dict[str, float]:
        return dict(self.per_axis_spread)


class EvaluationPanel:
    """Deterministic robust aggregation of independent evaluator verdicts."""

    def __init__(
        self,
        evaluator_ids: Iterable[str],
        *,
        minimum_quorum: int = 3,
        minimum_confidence: float = 0.55,
        max_axis_disagreement: float = 0.25,
        minimum_method_diversity: int = 2,
    ) -> None:
        ids = tuple(str(x).strip() for x in evaluator_ids)
        if len(ids) != len(set(ids)) or any(not x for x in ids):
            raise ValueError("evaluator identities must be unique and non-empty")
        if any(x in {Rival.A.value, Rival.B.value} for x in ids):
            raise ValueError("rivals cannot join the independent evaluator panel")
        if minimum_quorum < 3 or minimum_quorum > len(ids):
            raise ValueError("minimum_quorum must be >=3 and <= evaluator count")
        if minimum_method_diversity < 1 or minimum_method_diversity > minimum_quorum:
            raise ValueError("invalid minimum_method_diversity")
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be within [0,1]")
        if not 0.0 <= max_axis_disagreement <= 1.0:
            raise ValueError("max_axis_disagreement must be within [0,1]")
        self.evaluator_ids = ids
        self.minimum_quorum = minimum_quorum
        self.minimum_confidence = float(minimum_confidence)
        self.max_axis_disagreement = float(max_axis_disagreement)
        self.minimum_method_diversity = minimum_method_diversity
        self._verdicts: dict[tuple[str, str], JudgeVerdict] = {}

    def submit(self, verdict: JudgeVerdict) -> None:
        if verdict.evaluator_id not in self.evaluator_ids:
            raise EvaluationError("verdict evaluator is not a panel member")
        key = (verdict.candidate_digest, verdict.evaluator_id)
        if key in self._verdicts:
            raise EvaluationError("duplicate evaluator verdict for candidate")
        self._verdicts[key] = verdict

    def verdicts_for(self, candidate_digest: str) -> tuple[JudgeVerdict, ...]:
        return tuple(
            self._verdicts[(candidate_digest, evaluator)]
            for evaluator in self.evaluator_ids
            if (candidate_digest, evaluator) in self._verdicts
        )

    def decide(self, candidate_digest: str) -> PanelDecision:
        rows = self.verdicts_for(candidate_digest)
        if len(rows) < self.minimum_quorum:
            raise EvaluationError("independent evaluator quorum is not satisfied")

        aggregate: list[tuple[str, float]] = []
        spreads: list[tuple[str, float]] = []
        disagreement_axes: list[str] = []
        for axis in QUALITY_AXES:
            values = [row.quality_map[axis] for row in rows]
            aggregate.append((axis, float(median(values))))
            spread = max(values) - min(values)
            spreads.append((axis, spread))
            if spread > self.max_axis_disagreement:
                disagreement_axes.append(axis)

        confidences = [row.confidence for row in rows]
        methods = tuple(sorted({row.method_id for row in rows}))
        confidence_floor = min(confidences)
        confidence_ok = confidence_floor >= self.minimum_confidence
        method_ok = len(methods) >= self.minimum_method_diversity
        disagreement_ok = not disagreement_axes
        eligible = confidence_ok and method_ok and disagreement_ok
        requires_appeal = not eligible
        payload = {
            "aggregate_quality": dict(aggregate),
            "candidate_digest": candidate_digest,
            "disagreement_axes": disagreement_axes,
            "evaluator_ids": [row.evaluator_id for row in rows],
            "evaluator_verdict_digests": [row.digest for row in rows],
            "eligible": eligible,
            "max_axis_disagreement": self.max_axis_disagreement,
            "median_confidence": float(median(confidences)),
            "methods": list(methods),
            "minimum_confidence": confidence_floor,
            "requires_appeal": requires_appeal,
        }
        return PanelDecision(
            candidate_digest=candidate_digest,
            evaluator_ids=tuple(row.evaluator_id for row in rows),
            method_ids=methods,
            aggregate_quality=tuple(aggregate),
            per_axis_spread=tuple(spreads),
            median_confidence=float(median(confidences)),
            minimum_confidence=confidence_floor,
            max_disagreement=max(value for _, value in spreads),
            disagreement_axes=tuple(disagreement_axes),
            eligible=eligible,
            requires_appeal=requires_appeal,
            decision_digest=canonical_digest(payload),
        )


def blind_candidate_token(candidate_digest: str, *, salt: str) -> str:
    """Create deterministic evaluator-facing identity without exposing rival identity."""

    if len(candidate_digest) < 16:
        raise ValueError("candidate_digest must be stable")
    if len(salt) < 16:
        raise ValueError("blind-evaluation salt must be stable")
    return "blind-" + canonical_digest({"candidate": candidate_digest, "salt": salt})[:24]
