"""P1 answer/artifact quality qualification.

This module composes the existing QualityReport contract with explicit
independent-evaluator identity, materialized EvidenceRef provenance, declared
artifact coverage, and reasoning-regression evidence.  It does not generate
answers, score itself, mutate masterplan maturity, or treat model
self-confidence as verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef, evidence_ref_identity
from skeleton.intelligence.quality import QualityReport


OUTPUT_QUALITY_SCHEMA_VERSION = 1
OUTPUT_QUALITY_TASK_ID = "P1-INTEL-04"
OUTPUT_QUALITY_ACCOUNTABILITY_ID = "ACC-P1-INTEL-04"


class OutputQualityError(ValueError):
    """Answer/artifact quality evidence is malformed or non-authoritative."""


class OutputKind(str, Enum):
    ANSWER = "answer"
    ARTIFACT = "artifact"


class OutputDisposition(str, Enum):
    BLOCKED = "blocked"
    QUALIFIED = "qualified"
    ABSTAINED = "abstained"


class ArtifactType(str, Enum):
    CODE = "code"
    DOCUMENT = "document"
    DATA = "data"
    MODEL = "model"
    CONFIGURATION = "configuration"
    BINARY = "binary"


class ChangeImpact(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_ARTIFACT_TYPE_GATES: dict[ArtifactType, tuple[str, ...]] = {
    ArtifactType.CODE: ("static-analysis", "tests"),
    ArtifactType.DOCUMENT: ("factuality", "link-integrity"),
    ArtifactType.DATA: ("schema", "provenance"),
    ArtifactType.MODEL: ("evaluation", "safety"),
    ArtifactType.CONFIGURATION: ("schema", "rollback"),
    ArtifactType.BINARY: ("provenance", "malware"),
}
_IMPACT_GATES: dict[ChangeImpact, tuple[str, ...]] = {
    ChangeImpact.LOW: (),
    ChangeImpact.MEDIUM: ("change-impact-review",),
    ChangeImpact.HIGH: ("change-impact-review", "security", "rollback"),
    ChangeImpact.CRITICAL: (
        "change-impact-review",
        "security",
        "rollback",
        "independent-release",
    ),
}


def required_artifact_gates(
    artifact_type: ArtifactType | str,
    change_impact: ChangeImpact | str,
) -> tuple[str, ...]:
    try:
        kind = ArtifactType(artifact_type)
        impact = ChangeImpact(change_impact)
    except ValueError as exc:
        raise OutputQualityError("invalid artifact gate profile") from exc
    return tuple(
        sorted(
            set(_ARTIFACT_TYPE_GATES[kind])
            | set(_IMPACT_GATES[impact])
        )
    )


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OutputQualityError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise OutputQualityError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise OutputQualityError(f"{field} must be lowercase sha256")
    return text


def _score(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OutputQualityError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise OutputQualityError(f"{field} must be within [0, 1]")
    return result


def _canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise OutputQualityError("quality payload must be canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _refs(values: Iterable[EvidenceRef], field: str) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise OutputQualityError(f"{field} must contain EvidenceRef")
    by_identity: dict[str, EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise OutputQualityError(f"{field} must contain EvidenceRef")
        _text(item.source, f"{field}.source", maximum=2048)
        _sha256(item.digest, f"{field}.digest")
        _text(item.category, f"{field}.category", maximum=128)
        by_identity[evidence_ref_identity(item)] = item
    if not by_identity:
        raise OutputQualityError(f"{field} requires materialized evidence")
    return tuple(by_identity[key] for key in sorted(by_identity))


def _refs_payload(values: tuple[EvidenceRef, ...]) -> list[dict[str, str]]:
    return [
        {
            "identity": evidence_ref_identity(item),
            "source": item.source,
            "digest": item.digest,
            "category": item.category,
        }
        for item in values
    ]


def _quality_report_payload(report: QualityReport) -> dict[str, Any]:
    if not isinstance(report, QualityReport):
        raise OutputQualityError("report must be QualityReport")
    if not isinstance(report.accepted, bool):
        raise OutputQualityError("report.accepted must be boolean")
    _text(report.reason, "report.reason", maximum=4096)
    _score(report.score, "report.score")
    if not isinstance(report.metadata, Mapping):
        raise OutputQualityError("report.metadata must be a mapping")
    payload = report.to_dict()
    # Force deterministic JSON validation and reject non-finite nested values.
    _canonical_digest(payload)
    return payload


def _self_confidence_only(report: QualityReport) -> bool:
    metadata = dict(report.metadata)
    if metadata.get("self_confidence_only") is True:
        return True
    source = metadata.get("quality_source")
    return source in {"self_confidence", "model_self_report", "generator_confidence"}


@dataclass(frozen=True, slots=True)
class IndependentQualityEvaluation:
    kind: OutputKind
    subject_id: str
    subject_digest: str
    evaluator_id: str
    evaluator_digest: str
    report: QualityReport
    evidence_refs: tuple[EvidenceRef, ...]
    independent: bool = True
    artifact_type: ArtifactType | None = None
    change_impact: ChangeImpact | None = None
    published_subject_digest: str | None = None
    gate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "kind", OutputKind(self.kind))
        except ValueError as exc:
            raise OutputQualityError("invalid output kind") from exc
        object.__setattr__(
            self, "subject_id", _text(self.subject_id, "subject_id", maximum=512)
        )
        object.__setattr__(
            self,
            "subject_digest",
            _sha256(self.subject_digest, "subject_digest"),
        )
        object.__setattr__(
            self, "evaluator_id", _text(self.evaluator_id, "evaluator_id", maximum=512)
        )
        object.__setattr__(
            self,
            "evaluator_digest",
            _sha256(self.evaluator_digest, "evaluator_digest"),
        )
        _quality_report_payload(self.report)
        if not isinstance(self.independent, bool):
            raise OutputQualityError("independent must be boolean")
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "quality evidence"),
        )
        if self.kind is OutputKind.ARTIFACT:
            if self.artifact_type is None or self.change_impact is None:
                raise OutputQualityError(
                    "artifact evaluation requires artifact_type and change_impact"
                )
            try:
                object.__setattr__(
                    self,
                    "artifact_type",
                    ArtifactType(self.artifact_type),
                )
                object.__setattr__(
                    self,
                    "change_impact",
                    ChangeImpact(self.change_impact),
                )
            except ValueError as exc:
                raise OutputQualityError(
                    "invalid artifact type or change impact"
                ) from exc
            if self.published_subject_digest is None:
                raise OutputQualityError(
                    "artifact evaluation requires published_subject_digest"
                )
            object.__setattr__(
                self,
                "published_subject_digest",
                _sha256(
                    self.published_subject_digest,
                    "published_subject_digest",
                ),
            )
            gates = tuple(
                sorted(
                    {
                        _text(item, "gate_id", maximum=128)
                        for item in self.gate_ids
                    }
                )
            )
            if not gates:
                raise OutputQualityError(
                    "artifact evaluation requires gate_ids"
                )
            object.__setattr__(self, "gate_ids", gates)
        else:
            if (
                self.artifact_type is not None
                or self.change_impact is not None
                or self.published_subject_digest is not None
                or self.gate_ids
            ):
                raise OutputQualityError(
                    "answer evaluation cannot carry artifact gate metadata"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "subject_id": self.subject_id,
            "subject_digest": self.subject_digest,
            "evaluator_id": self.evaluator_id,
            "evaluator_digest": self.evaluator_digest,
            "independent": self.independent,
            "artifact_type": (
                self.artifact_type.value
                if self.artifact_type is not None
                else None
            ),
            "change_impact": (
                self.change_impact.value
                if self.change_impact is not None
                else None
            ),
            "published_subject_digest": self.published_subject_digest,
            "gate_ids": list(self.gate_ids),
            "report": _quality_report_payload(self.report),
            "evidence_refs": _refs_payload(self.evidence_refs),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ReasoningRegressionObservation:
    suite_id: str
    baseline_digest: str
    candidate_digest: str
    baseline_score: float
    candidate_score: float
    max_allowed_drop: float
    evaluator_id: str
    evaluator_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    independent: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "suite_id", _text(self.suite_id, "suite_id"))
        object.__setattr__(
            self, "baseline_digest", _sha256(self.baseline_digest, "baseline_digest")
        )
        object.__setattr__(
            self, "candidate_digest", _sha256(self.candidate_digest, "candidate_digest")
        )
        object.__setattr__(
            self, "baseline_score", _score(self.baseline_score, "baseline_score")
        )
        object.__setattr__(
            self, "candidate_score", _score(self.candidate_score, "candidate_score")
        )
        drop = _score(self.max_allowed_drop, "max_allowed_drop")
        object.__setattr__(self, "max_allowed_drop", drop)
        object.__setattr__(
            self, "evaluator_id", _text(self.evaluator_id, "evaluator_id")
        )
        object.__setattr__(
            self,
            "evaluator_digest",
            _sha256(self.evaluator_digest, "evaluator_digest"),
        )
        if not isinstance(self.independent, bool):
            raise OutputQualityError("independent must be boolean")
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "regression evidence"),
        )

    @property
    def passed(self) -> bool:
        return self.candidate_score + self.max_allowed_drop >= self.baseline_score

    def payload(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "baseline_digest": self.baseline_digest,
            "candidate_digest": self.candidate_digest,
            "baseline_score": self.baseline_score,
            "candidate_score": self.candidate_score,
            "max_allowed_drop": self.max_allowed_drop,
            "evaluator_id": self.evaluator_id,
            "evaluator_digest": self.evaluator_digest,
            "independent": self.independent,
            "passed": self.passed,
            "evidence_refs": _refs_payload(self.evidence_refs),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class OutputQualityPolicy:
    min_answer_score: float = 0.80
    min_artifact_score: float = 0.80
    require_reasoning_regression: bool = True
    require_independent: bool = True
    require_artifact_publication_binding: bool = True
    require_artifact_gate_coverage: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "min_answer_score", _score(self.min_answer_score, "min_answer_score")
        )
        object.__setattr__(
            self,
            "min_artifact_score",
            _score(self.min_artifact_score, "min_artifact_score"),
        )
        for field in (
            "require_reasoning_regression",
            "require_independent",
            "require_artifact_publication_binding",
            "require_artifact_gate_coverage",
        ):
            if not isinstance(getattr(self, field), bool):
                raise OutputQualityError(f"{field} must be boolean")

    def payload(self) -> dict[str, Any]:
        return {
            "min_answer_score": self.min_answer_score,
            "min_artifact_score": self.min_artifact_score,
            "require_reasoning_regression": self.require_reasoning_regression,
            "require_independent": self.require_independent,
            "require_artifact_publication_binding": (
                self.require_artifact_publication_binding
            ),
            "require_artifact_gate_coverage": (
                self.require_artifact_gate_coverage
            ),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class AnswerArtifactQualityDecision:
    accepted: bool
    disposition: OutputDisposition
    reasons: tuple[str, ...]
    answer_evaluation_digest: str
    artifact_evaluation_digests: tuple[str, ...]
    regression_digests: tuple[str, ...]
    policy_digest: str
    task_id: str = OUTPUT_QUALITY_TASK_ID
    accountability_id: str = OUTPUT_QUALITY_ACCOUNTABILITY_ID
    schema_version: int = OUTPUT_QUALITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise OutputQualityError("accepted must be boolean")
        try:
            object.__setattr__(
                self,
                "disposition",
                OutputDisposition(self.disposition),
            )
        except ValueError as exc:
            raise OutputQualityError("invalid output disposition") from exc
        if self.accepted != (
            self.disposition is OutputDisposition.QUALIFIED
        ):
            raise OutputQualityError(
                "accepted must exactly match qualified disposition"
            )
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise OutputQualityError("reasons must contain non-empty strings")
        object.__setattr__(
            self,
            "answer_evaluation_digest",
            _sha256(self.answer_evaluation_digest, "answer_evaluation_digest"),
        )
        for field in ("artifact_evaluation_digests", "regression_digests"):
            values = getattr(self, field)
            if not isinstance(values, tuple):
                raise OutputQualityError(f"{field} must be a tuple")
            normalized = tuple(sorted({_sha256(item, field) for item in values}))
            object.__setattr__(self, field, normalized)
        object.__setattr__(
            self, "policy_digest", _sha256(self.policy_digest, "policy_digest")
        )
        if self.task_id != OUTPUT_QUALITY_TASK_ID:
            raise OutputQualityError("task_id drift")
        if self.accountability_id != OUTPUT_QUALITY_ACCOUNTABILITY_ID:
            raise OutputQualityError("accountability_id drift")
        if self.schema_version != OUTPUT_QUALITY_SCHEMA_VERSION:
            raise OutputQualityError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "disposition": self.disposition.value,
            "publication_allowed": (
                self.disposition is OutputDisposition.QUALIFIED
            ),
            "reasons": list(self.reasons),
            "answer_evaluation_digest": self.answer_evaluation_digest,
            "artifact_evaluation_digests": list(self.artifact_evaluation_digests),
            "regression_digests": list(self.regression_digests),
            "policy_digest": self.policy_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:intel-04:answer-artifact-quality",
    ) -> EvidenceRef:
        if (
            not self.accepted
            or self.disposition is not OutputDisposition.QUALIFIED
        ):
            raise OutputQualityError(
                "only qualified output quality decision can become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source", maximum=2048),
            digest=self.decision_digest,
            category="answer_artifact_quality",
        )


def evaluate_answer_artifact_quality(
    *,
    answer: IndependentQualityEvaluation,
    artifacts: Iterable[IndependentQualityEvaluation] = (),
    expected_artifact_digests: Iterable[str] = (),
    reasoning_regressions: Iterable[ReasoningRegressionObservation] = (),
    policy: OutputQualityPolicy | None = None,
    answer_disposition: OutputDisposition = OutputDisposition.QUALIFIED,
) -> AnswerArtifactQualityDecision:
    if not isinstance(answer, IndependentQualityEvaluation):
        raise TypeError("answer must be IndependentQualityEvaluation")
    if answer.kind is not OutputKind.ANSWER:
        raise OutputQualityError("answer evaluation must have kind=answer")
    active_policy = policy or OutputQualityPolicy()
    if not isinstance(active_policy, OutputQualityPolicy):
        raise TypeError("policy must be OutputQualityPolicy")
    try:
        requested_disposition = OutputDisposition(answer_disposition)
    except ValueError as exc:
        raise OutputQualityError("invalid answer_disposition") from exc

    artifact_items = tuple(artifacts)
    if any(not isinstance(item, IndependentQualityEvaluation) for item in artifact_items):
        raise OutputQualityError("artifacts must contain IndependentQualityEvaluation")
    if any(item.kind is not OutputKind.ARTIFACT for item in artifact_items):
        raise OutputQualityError("artifact evaluations must have kind=artifact")
    artifact_by_subject: dict[str, IndependentQualityEvaluation] = {}
    for item in artifact_items:
        if item.subject_digest in artifact_by_subject:
            raise OutputQualityError("duplicate artifact subject digest")
        artifact_by_subject[item.subject_digest] = item

    expected = tuple(
        sorted({_sha256(item, "expected_artifact_digests") for item in expected_artifact_digests})
    )
    actual = tuple(sorted(artifact_by_subject))
    regressions = tuple(reasoning_regressions)
    if any(not isinstance(item, ReasoningRegressionObservation) for item in regressions):
        raise OutputQualityError(
            "reasoning_regressions must contain ReasoningRegressionObservation"
        )

    reasons: list[str] = []

    if active_policy.require_independent and not answer.independent:
        reasons.append("answer-evaluator-not-independent")
    if _self_confidence_only(answer.report):
        reasons.append("answer-self-confidence-is-not-verification")
    if not answer.report.accepted:
        reasons.append("answer-quality-rejected")
    if answer.report.score < active_policy.min_answer_score:
        reasons.append("answer-quality-below-threshold")

    if expected != actual:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing:
            reasons.append("artifact-quality-missing:" + ",".join(missing))
        if extra:
            reasons.append("artifact-quality-unexpected:" + ",".join(extra))

    for item in artifact_items:
        if active_policy.require_independent and not item.independent:
            reasons.append(f"artifact-evaluator-not-independent:{item.subject_id}")
        if _self_confidence_only(item.report):
            reasons.append(f"artifact-self-confidence-is-not-verification:{item.subject_id}")
        if not item.report.accepted:
            reasons.append(f"artifact-quality-rejected:{item.subject_id}")
        if item.report.score < active_policy.min_artifact_score:
            reasons.append(f"artifact-quality-below-threshold:{item.subject_id}")
        if (
            active_policy.require_artifact_publication_binding
            and item.published_subject_digest != item.subject_digest
        ):
            reasons.append(
                f"artifact-published-digest-mismatch:{item.subject_id}"
            )
        if active_policy.require_artifact_gate_coverage:
            required = set(
                required_artifact_gates(
                    item.artifact_type,
                    item.change_impact,
                )
            )
            missing_gates = sorted(required - set(item.gate_ids))
            if missing_gates:
                reasons.append(
                    "artifact-required-gates-missing:"
                    + item.subject_id
                    + ":"
                    + ",".join(missing_gates)
                )

    if active_policy.require_reasoning_regression and not regressions:
        reasons.append("reasoning-regression-evidence-missing")
    for item in regressions:
        if active_policy.require_independent and not item.independent:
            reasons.append(f"reasoning-regression-not-independent:{item.suite_id}")
        if not item.passed:
            reasons.append(f"reasoning-regression-exceeded:{item.suite_id}")

    if requested_disposition is OutputDisposition.ABSTAINED:
        reasons.append("answer-abstained")
        final_disposition = OutputDisposition.ABSTAINED
    elif requested_disposition is OutputDisposition.BLOCKED:
        reasons.append("answer-explicitly-blocked")
        final_disposition = OutputDisposition.BLOCKED
    else:
        final_disposition = (
            OutputDisposition.QUALIFIED
            if not reasons
            else OutputDisposition.BLOCKED
        )

    normalized = tuple(sorted(set(reasons)))
    return AnswerArtifactQualityDecision(
        accepted=final_disposition is OutputDisposition.QUALIFIED,
        disposition=final_disposition,
        reasons=normalized,
        answer_evaluation_digest=answer.digest,
        artifact_evaluation_digests=tuple(item.digest for item in artifact_items),
        regression_digests=tuple(item.digest for item in regressions),
        policy_digest=active_policy.digest,
    )


__all__ = [
    "OUTPUT_QUALITY_ACCOUNTABILITY_ID",
    "OUTPUT_QUALITY_SCHEMA_VERSION",
    "OUTPUT_QUALITY_TASK_ID",
    "AnswerArtifactQualityDecision",
    "ArtifactType",
    "ChangeImpact",
    "IndependentQualityEvaluation",
    "OutputDisposition",
    "OutputKind",
    "OutputQualityError",
    "OutputQualityPolicy",
    "ReasoningRegressionObservation",
    "evaluate_answer_artifact_quality",
    "required_artifact_gates",
]
