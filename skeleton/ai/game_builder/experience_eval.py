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

from .contracts import EvaluatorProvenance, Rival, canonical_digest


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
    evaluator_provenance: EvaluatorProvenance
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _text(self.observation_id, "observation_id"))
        object.__setattr__(self, "artifact_digest", _digest(self.artifact_digest, "artifact_digest"))
        object.__setattr__(self, "project_revision", _text(self.project_revision, "project_revision"))
        evaluator_id = _text(self.evaluator_id, "evaluator_id")
        method_id = _text(self.method_id, "method_id")
        if evaluator_id in {Rival.A.value, Rival.B.value}:
            raise ValueError("experience evaluator must be independent from both rivals")
        if not isinstance(self.evaluator_provenance, EvaluatorProvenance):
            raise TypeError("experience evaluator_provenance must be EvaluatorProvenance")
        if evaluator_id != self.evaluator_provenance.evaluator_id:
            raise ExperienceEvaluationError("experience evaluator identity does not match provenance")
        if method_id != self.evaluator_provenance.method_id:
            raise ExperienceEvaluationError("experience method identity does not match provenance")
        object.__setattr__(self, "evaluator_id", evaluator_id)
        object.__setattr__(self, "method_id", method_id)
        object.__setattr__(self, "atomic_target_id", _text(self.atomic_target_id, "atomic_target_id"))

        parents = tuple(_text(value, "parent_context") for value in self.parent_context)
        facts = tuple(_text(value, "observed_fact", max_length=2048) for value in self.observed_facts)
        interpretations = tuple(
            _text(value, "interpretation", max_length=2048)
            for value in self.interpretations
        )
        if not parents:
            raise ValueError("atomic observation requires parent context")
        if not facts:
            raise ValueError("observed_facts must be non-empty")
        if len(parents) != len(set(parents)):
            raise ValueError("parent_context identities must be unique")
        object.__setattr__(self, "parent_context", parents)
        object.__setattr__(self, "observed_facts", facts)
        object.__setattr__(self, "interpretations", interpretations)

        raw_metrics = tuple(self.metrics)
        if len(raw_metrics) != len({name for name, _ in raw_metrics}):
            raise ValueError("experience metric names must be unique")
        normalized_metrics = normalize_experience_metrics(dict(raw_metrics))
        object.__setattr__(self, "metrics", normalized_metrics)

        evidence_digest = _digest(self.evidence_digest, "evidence_digest")
        if evidence_digest not in self.evaluator_provenance.output_evidence_refs:
            raise ExperienceEvaluationError(
                "experience evidence must be referenced by evaluator authority"
            )
        object.__setattr__(self, "evidence_digest", evidence_digest)

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
        evaluator_provenance: EvaluatorProvenance,
        evidence_digest: str,
    ) -> "ExperienceObservation":
        return cls(
            observation_id=observation_id,
            artifact_digest=artifact_digest,
            project_revision=project_revision,
            evaluator_id=evaluator_id,
            method_id=method_id,
            atomic_target_id=atomic_target_id,
            parent_context=tuple(parent_context),
            observed_facts=tuple(observed_facts),
            interpretations=tuple(interpretations),
            metrics=tuple(metrics.items()),
            evaluator_provenance=evaluator_provenance,
            evidence_digest=evidence_digest,
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
                "evaluator_provenance_digest": self.evaluator_provenance.digest,
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
    evaluator_provenance: EvaluatorProvenance
    resolved_by_digest: str | None = None
    resolution_authority: EvaluatorProvenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "defect_id", _text(self.defect_id, "defect_id"))
        object.__setattr__(self, "artifact_digest", _digest(self.artifact_digest, "artifact_digest"))
        object.__setattr__(self, "summary", _text(self.summary, "summary", max_length=2048))
        object.__setattr__(self, "evidence_digest", _digest(self.evidence_digest, "evidence_digest"))
        if self.severity not in (1, 2, 4, 8):
            raise ValueError("severity must be one of 1,2,4,8")
        if not self.affected_context:
            raise ValueError("affected_context must be non-empty")
        context = tuple(_text(value, "affected_context") for value in self.affected_context)
        if len(context) != len(set(context)):
            raise ValueError("affected_context identities must be unique")
        object.__setattr__(self, "affected_context", context)
        if not isinstance(self.evaluator_provenance, EvaluatorProvenance):
            raise TypeError("defect evaluator_provenance must be EvaluatorProvenance")
        if self.evidence_digest not in self.evaluator_provenance.output_evidence_refs:
            raise ExperienceEvaluationError(
                "defect evidence must be referenced by evaluator authority"
            )

        if self.resolved_by_digest is None:
            if self.resolution_authority is not None:
                raise ValueError("unresolved defect cannot carry resolution authority")
        else:
            object.__setattr__(
                self,
                "resolved_by_digest",
                _digest(self.resolved_by_digest, "resolved_by_digest"),
            )
            if not isinstance(self.resolution_authority, EvaluatorProvenance):
                raise TypeError("resolved defect requires resolution authority")
            if self.resolved_by_digest not in self.resolution_authority.output_evidence_refs:
                raise ExperienceEvaluationError(
                    "defect resolution evidence must be referenced by resolution authority"
                )
            if (
                self.severity >= 8
                and self.resolution_authority.evaluator_id
                == self.evaluator_provenance.evaluator_id
            ):
                raise ExperienceEvaluationError(
                    "critical defect resolution requires independent authority"
                )

    @property
    def unresolved(self) -> bool:
        return self.resolved_by_digest is None

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "affected_context": list(self.affected_context),
                "artifact_digest": self.artifact_digest,
                "defect_id": self.defect_id,
                "evaluator_provenance_digest": self.evaluator_provenance.digest,
                "evidence_digest": self.evidence_digest,
                "resolution_authority_digest": (
                    None
                    if self.resolution_authority is None
                    else self.resolution_authority.digest
                ),
                "resolved_by_digest": self.resolved_by_digest,
                "severity": self.severity,
                "summary": self.summary,
            }
        )


@dataclass(frozen=True, slots=True)
class ExperienceReport:
    artifact_digest: str
    project_revision: str
    evaluator_ids: tuple[str, ...]
    observation_digests: tuple[str, ...]
    defect_digests: tuple[str, ...]
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
        "defect_digests": sorted(defect.digest for defect in defect_rows),
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
        defect_digests=tuple(core["defect_digests"]),
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
