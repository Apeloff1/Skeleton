"""Player-value and experience QA primitives for the dual-rival game builder.

GB48 owns observation/evidence capture for player-facing quality.  This module
keeps observed facts separate from interpretation, preserves atomic-to-global
traceability, and fails closed when a candidate regresses any protected
experience metric or carries unresolved critical defects.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, Mapping

from .contracts import Rival, canonical_digest


class ExperienceEvaluationError(RuntimeError):
    """Raised when governed experience evidence is malformed or unsafe."""


EXPERIENCE_METRICS = (
    "engagement_proxy",
    "friction_detection",
    "learning_curve",
    "player_value_density",
)


def _text(value: object, label: str, *, max_length: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > max_length
    ):
        raise ValueError(f"{label} must be non-empty normalized text")
    return value


def _digest(value: object, label: str) -> str:
    value = _text(value, label)
    if len(value) < 16:
        raise ValueError(f"{label} must be a stable digest")
    return value


def _score(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"{label} must be within [0,1]")
    return score


def normalize_experience_metrics(values: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    if set(values) != set(EXPERIENCE_METRICS):
        missing = sorted(set(EXPERIENCE_METRICS) - set(values))
        extra = sorted(set(values) - set(EXPERIENCE_METRICS))
        raise ValueError(f"experience metric contract drift missing={missing} extra={extra}")
    return tuple((name, _score(values[name], name)) for name in EXPERIENCE_METRICS)


@dataclass(frozen=True, slots=True)
class ExperienceObservation:
    observation_id: str
    artifact_digest: str
    project_revision: str
    evaluator_id: str
    method_id: str
    atomic_target_id: str
    parent_context: tuple[str, ...]
    observed_facts: tuple[str, ...]
    interpretations: tuple[str, ...]
    metrics: tuple[tuple[str, float], ...]
    evidence_digest: str

    @classmethod
    def create(
        cls,
        *,
        observation_id: str,
        artifact_digest: str,
        project_revision: str,
        evaluator_id: str,
        method_id: str,
        atomic_target_id: str,
        parent_context: Iterable[str],
        observed_facts: Iterable[str],
        interpretations: Iterable[str],
        metrics: Mapping[str, float],
        evidence_digest: str,
    ) -> "ExperienceObservation":
        parents = tuple(_text(value, "parent_context") for value in parent_context)
        facts = tuple(_text(value, "observed_fact", max_length=2048) for value in observed_facts)
        interpretations_tuple = tuple(
            _text(value, "interpretation", max_length=2048) for value in interpretations
        )
        if not parents:
            raise ValueError("atomic observation requires parent context")
        if not facts:
            raise ValueError("observed_facts must be non-empty")
        if len(parents) != len(set(parents)):
            raise ValueError("parent_context identities must be unique")
        normalized_evaluator = _text(evaluator_id, "evaluator_id")
        if normalized_evaluator in {Rival.A.value, Rival.B.value}:
            raise ValueError("experience evaluator must be independent from both rivals")
        return cls(
            observation_id=_text(observation_id, "observation_id"),
            artifact_digest=_digest(artifact_digest, "artifact_digest"),
            project_revision=_text(project_revision, "project_revision"),
            evaluator_id=normalized_evaluator,
            method_id=_text(method_id, "method_id"),
            atomic_target_id=_text(atomic_target_id, "atomic_target_id"),
            parent_context=parents,
            observed_facts=facts,
            interpretations=interpretations_tuple,
            metrics=normalize_experience_metrics(metrics),
            evidence_digest=_digest(evidence_digest, "evidence_digest"),
        )

    @property
    def metric_map(self) -> dict[str, float]:
        return dict(self.metrics)

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "artifact_digest": self.artifact_digest,
                "atomic_target_id": self.atomic_target_id,
                "evaluator_id": self.evaluator_id,
                "evidence_digest": self.evidence_digest,
                "interpretations": list(self.interpretations),
                "method_id": self.method_id,
                "metrics": dict(self.metrics),
                "observation_id": self.observation_id,
                "observed_facts": list(self.observed_facts),
                "parent_context": list(self.parent_context),
                "project_revision": self.project_revision,
            }
        )


@dataclass(frozen=True, slots=True)
class ExperienceDefect:
    defect_id: str
    artifact_digest: str
    severity: int
    summary: str
    evidence_digest: str
    affected_context: tuple[str, ...]
    resolved_by_digest: str | None = None

    def __post_init__(self) -> None:
        _text(self.defect_id, "defect_id")
        _digest(self.artifact_digest, "artifact_digest")
        _text(self.summary, "summary", max_length=2048)
        _digest(self.evidence_digest, "evidence_digest")
        if self.severity not in (1, 2, 4, 8):
            raise ValueError("severity must be one of 1,2,4,8")
        if not self.affected_context:
            raise ValueError("affected_context must be non-empty")
        for value in self.affected_context:
            _text(value, "affected_context")
        if self.resolved_by_digest is not None:
            _digest(self.resolved_by_digest, "resolved_by_digest")

    @property
    def unresolved(self) -> bool:
        return self.resolved_by_digest is None


@dataclass(frozen=True, slots=True)
class ExperienceReport:
    artifact_digest: str
    project_revision: str
    evaluator_ids: tuple[str, ...]
    observation_digests: tuple[str, ...]
    aggregate_metrics: tuple[tuple[str, float], ...]
    unresolved_critical_defects: tuple[str, ...]
    report_digest: str

    @property
    def metric_map(self) -> dict[str, float]:
        return dict(self.aggregate_metrics)

    @property
    def promotable(self) -> bool:
        return not self.unresolved_critical_defects


def build_experience_report(
    observations: Iterable[ExperienceObservation],
    *,
    defects: Iterable[ExperienceDefect] = (),
    minimum_evaluator_diversity: int = 2,
) -> ExperienceReport:
    rows = tuple(observations)
    if not rows:
        raise ExperienceEvaluationError("experience report requires observations")
    if minimum_evaluator_diversity < 1:
        raise ValueError("minimum_evaluator_diversity must be positive")

    artifact_ids = {row.artifact_digest for row in rows}
    revisions = {row.project_revision for row in rows}
    observation_ids = [row.observation_id for row in rows]
    if len(artifact_ids) != 1 or len(revisions) != 1:
        raise ExperienceEvaluationError("experience observations must share artifact/revision identity")
    if len(observation_ids) != len(set(observation_ids)):
        raise ExperienceEvaluationError("duplicate experience observation identity")

    evaluator_ids = tuple(sorted({row.evaluator_id for row in rows}))
    if len(evaluator_ids) < minimum_evaluator_diversity:
        raise ExperienceEvaluationError("independent evaluator diversity is insufficient")

    aggregate = tuple(
        (
            metric,
            float(median(row.metric_map[metric] for row in rows)),
        )
        for metric in EXPERIENCE_METRICS
    )

    defect_rows = tuple(defects)
    artifact_digest = next(iter(artifact_ids))
    for defect in defect_rows:
        if defect.artifact_digest != artifact_digest:
            raise ExperienceEvaluationError("defect artifact identity mismatch")
    critical = tuple(
        sorted(
            defect.defect_id
            for defect in defect_rows
            if defect.unresolved and defect.severity >= 8
        )
    )

    core = {
        "aggregate_metrics": dict(aggregate),
        "artifact_digest": artifact_digest,
        "evaluator_ids": list(evaluator_ids),
        "observation_digests": sorted(row.digest for row in rows),
        "project_revision": next(iter(revisions)),
        "unresolved_critical_defects": list(critical),
    }
    return ExperienceReport(
        artifact_digest=artifact_digest,
        project_revision=core["project_revision"],
        evaluator_ids=evaluator_ids,
        observation_digests=tuple(core["observation_digests"]),
        aggregate_metrics=aggregate,
        unresolved_critical_defects=critical,
        report_digest=canonical_digest(core),
    )


@dataclass(frozen=True, slots=True)
class ExperiencePromotionDecision:
    eligible: bool
    pareto_safe: bool
    improved_metrics: tuple[str, ...]
    regressed_metrics: tuple[str, ...]
    blockers: tuple[str, ...]
    decision_digest: str


def evaluate_experience_promotion(
    baseline: ExperienceReport,
    candidate: ExperienceReport,
) -> ExperiencePromotionDecision:
    if baseline.project_revision == candidate.project_revision and baseline.artifact_digest == candidate.artifact_digest:
        raise ExperienceEvaluationError("candidate must have a distinct artifact or project revision")

    regressions = tuple(
        metric
        for metric in EXPERIENCE_METRICS
        if candidate.metric_map[metric] < baseline.metric_map[metric]
    )
    improvements = tuple(
        metric
        for metric in EXPERIENCE_METRICS
        if candidate.metric_map[metric] > baseline.metric_map[metric]
    )
    blockers: list[str] = []
    if regressions:
        blockers.append("experience metric regression")
    if not improvements:
        blockers.append("candidate provides no measurable experience gain")
    if candidate.unresolved_critical_defects:
        blockers.append("candidate has unresolved critical experience defects")

    pareto_safe = not regressions and bool(improvements)
    eligible = pareto_safe and candidate.promotable
    core = {
        "baseline_report_digest": baseline.report_digest,
        "blockers": blockers,
        "candidate_report_digest": candidate.report_digest,
        "eligible": eligible,
        "improved_metrics": list(improvements),
        "pareto_safe": pareto_safe,
        "regressed_metrics": list(regressions),
    }
    return ExperiencePromotionDecision(
        eligible=eligible,
        pareto_safe=pareto_safe,
        improved_metrics=improvements,
        regressed_metrics=regressions,
        blockers=tuple(blockers),
        decision_digest=canonical_digest(core),
    )
