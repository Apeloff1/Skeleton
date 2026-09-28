"""P1 specification/adversarial/reasoning regression corpus.

Known failures are converted into immutable, promotion-blocking test cases.
Each case is bound to an EVID-04 risk obligation and an independent evaluator.
A qualification is accepted only when every required case has exactly one
matching observation with the declared safe outcome and a resolved blocking
risk binding.

This module is evaluation-only and cannot mutate candidate or maturity state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.risk_evidence import RiskBindingEvaluation
from skeleton.eval.benchmark_registry import BenchmarkQualificationDecision


REGRESSION_CORPUS_SCHEMA_VERSION = 1
REGRESSION_CORPUS_TASK_ID = "P1-LEARN-05"
REGRESSION_CORPUS_ACCOUNTABILITY_ID = "ACC-P1-LEARN-05"
_MAX_CASES = 2048
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RegressionCorpusError(ValueError):
    """Regression corpus input violates immutable evaluation policy."""


class FailureClass(str, Enum):
    SPECIFICATION_GAMING = "specification_gaming"
    REASONING_ERROR = "reasoning_error"
    GOAL_DRIFT = "goal_drift"
    POLICY_CONFLICT = "policy_conflict"
    DECEPTIVE_BEHAVIOR = "deceptive_behavior"
    PROMPT_INJECTION = "prompt_injection"
    EVIDENCE_SUBSTITUTION = "evidence_substitution"
    PRIVACY_BOUNDARY = "privacy_boundary"
    SIDE_EFFECT_ESCAPE = "side_effect_escape"


class SafeOutcome(str, Enum):
    REJECT = "reject"
    DEESCALATE = "deescalate"
    REQUIRE_HUMAN = "require_human"
    SAFE_COMPLETE = "safe_complete"
    NO_SIDE_EFFECT = "no_side_effect"


def _token(value: object, field: str, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise RegressionCorpusError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegressionCorpusError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise RegressionCorpusError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RegressionCorpusError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RegressionCorpusError(f"{field} must be a positive integer")
    return value


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RegressionCorpusError(
            "regression payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _tokens(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise RegressionCorpusError(f"{field} must be an iterable")
    result = tuple(sorted({_token(item, field) for item in values}))
    if not allow_empty and not result:
        raise RegressionCorpusError(f"{field} must be non-empty")
    return result


def _evidence(
    values: Iterable[EvidenceRef],
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise RegressionCorpusError(
            f"{field} must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise RegressionCorpusError(
                f"{field} must contain EvidenceRef values"
            )
        _text(item.source, f"{field}.source", maximum=2048)
        _sha256(item.digest, f"{field}.digest")
        _token(item.category, f"{field}.category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key and not allow_empty:
        raise RegressionCorpusError(f"{field} must be non-empty")
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class RegressionCase:
    case_id: str
    version: int
    failure_class: FailureClass
    description: str
    source_ref: str
    source_digest: str
    input_digest: str
    expected_outcome: SafeOutcome
    evaluator_id: str
    evaluator_digest: str
    risk_obligation_id: str
    risk_obligation_digest: str
    tags: tuple[str, ...] = ()
    promotion_blocking: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _token(self.case_id, "case_id"))
        object.__setattr__(
            self,
            "version",
            _positive_int(self.version, "version"),
        )
        try:
            object.__setattr__(
                self,
                "failure_class",
                FailureClass(self.failure_class),
            )
            object.__setattr__(
                self,
                "expected_outcome",
                SafeOutcome(self.expected_outcome),
            )
        except ValueError as exc:
            raise RegressionCorpusError("invalid regression enum") from exc
        object.__setattr__(
            self,
            "description",
            _text(self.description, "description"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _token(self.source_ref, "source_ref"),
        )
        for field in (
            "source_digest",
            "input_digest",
            "evaluator_digest",
            "risk_obligation_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "evaluator_id",
            _token(self.evaluator_id, "evaluator_id"),
        )
        object.__setattr__(
            self,
            "risk_obligation_id",
            _token(
                self.risk_obligation_id,
                "risk_obligation_id",
                maximum=320,
            ),
        )
        object.__setattr__(self, "tags", _tokens(self.tags, "tags"))
        if self.promotion_blocking is not True:
            raise RegressionCorpusError(
                "P1 regression cases must be promotion blocking"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "version": self.version,
            "failure_class": self.failure_class.value,
            "description": self.description,
            "source_ref": self.source_ref,
            "source_digest": self.source_digest,
            "input_digest": self.input_digest,
            "expected_outcome": self.expected_outcome.value,
            "evaluator_id": self.evaluator_id,
            "evaluator_digest": self.evaluator_digest,
            "risk_obligation_id": self.risk_obligation_id,
            "risk_obligation_digest": self.risk_obligation_digest,
            "tags": list(self.tags),
            "promotion_blocking": self.promotion_blocking,
        }

    @property
    def case_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class RegressionCorpus:
    corpus_id: str
    version: int
    cases: tuple[RegressionCase, ...]
    parent_corpus_digest: str | None = None
    schema_version: int = REGRESSION_CORPUS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "corpus_id",
            _token(self.corpus_id, "corpus_id"),
        )
        object.__setattr__(
            self,
            "version",
            _positive_int(self.version, "version"),
        )
        if (
            not isinstance(self.cases, tuple)
            or not self.cases
            or len(self.cases) > _MAX_CASES
        ):
            raise RegressionCorpusError(
                "cases must be a bounded non-empty tuple"
            )
        if any(not isinstance(item, RegressionCase) for item in self.cases):
            raise RegressionCorpusError(
                "cases must contain RegressionCase values"
            )
        keys = [(item.case_id, item.version) for item in self.cases]
        if len(keys) != len(set(keys)):
            raise RegressionCorpusError(
                "case id/version identities must be unique"
            )
        digests = [item.case_digest for item in self.cases]
        if len(digests) != len(set(digests)):
            raise RegressionCorpusError("case digests must be unique")
        obligations = [
            item.risk_obligation_id for item in self.cases
        ]
        if len(obligations) != len(set(obligations)):
            raise RegressionCorpusError(
                "risk obligations must be one-to-one with cases"
            )
        if self.parent_corpus_digest is not None:
            object.__setattr__(
                self,
                "parent_corpus_digest",
                _sha256(
                    self.parent_corpus_digest,
                    "parent_corpus_digest",
                ),
            )
        if self.schema_version != REGRESSION_CORPUS_SCHEMA_VERSION:
            raise RegressionCorpusError(
                "unsupported corpus schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": REGRESSION_CORPUS_TASK_ID,
            "accountability_id": REGRESSION_CORPUS_ACCOUNTABILITY_ID,
            "corpus_id": self.corpus_id,
            "version": self.version,
            "cases": [
                item.payload()
                for item in sorted(
                    self.cases,
                    key=lambda row: (row.case_id, row.version),
                )
            ],
            "parent_corpus_digest": self.parent_corpus_digest,
            "production_authority": False,
        }

    @property
    def corpus_digest(self) -> str:
        return _canonical_digest(self.payload())

    def case(self, case_id: str, version: int) -> RegressionCase:
        key = (_token(case_id, "case_id"), _positive_int(version, "version"))
        for item in self.cases:
            if (item.case_id, item.version) == key:
                return item
        raise KeyError(key)


@dataclass(frozen=True, slots=True)
class RegressionObservation:
    case_digest: str
    candidate_digest: str
    actual_outcome: SafeOutcome
    evaluator_id: str
    evaluator_digest: str
    output_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    independent: bool = True
    side_effect_count: int = 0

    def __post_init__(self) -> None:
        for field in (
            "case_digest",
            "candidate_digest",
            "evaluator_digest",
            "output_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        try:
            object.__setattr__(
                self,
                "actual_outcome",
                SafeOutcome(self.actual_outcome),
            )
        except ValueError as exc:
            raise RegressionCorpusError("invalid actual_outcome") from exc
        object.__setattr__(
            self,
            "evaluator_id",
            _token(self.evaluator_id, "evaluator_id"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs, "evidence_refs"),
        )
        if self.independent is not True:
            raise RegressionCorpusError(
                "regression observation must be independent"
            )
        if (
            isinstance(self.side_effect_count, bool)
            or not isinstance(self.side_effect_count, int)
            or self.side_effect_count != 0
        ):
            raise RegressionCorpusError(
                "regression evaluation cannot create side effects"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "case_digest": self.case_digest,
            "candidate_digest": self.candidate_digest,
            "actual_outcome": self.actual_outcome.value,
            "evaluator_id": self.evaluator_id,
            "evaluator_digest": self.evaluator_digest,
            "output_digest": self.output_digest,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
            "independent": self.independent,
            "side_effect_count": self.side_effect_count,
        }

    @property
    def observation_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class RegressionQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    corpus_digest: str
    candidate_digest: str
    benchmark_qualification_digest: str
    observation_digests: tuple[str, ...]
    risk_evaluation_digests: tuple[str, ...]
    passed_case_digests: tuple[str, ...]
    failed_case_digests: tuple[str, ...]
    task_id: str = REGRESSION_CORPUS_TASK_ID
    accountability_id: str = REGRESSION_CORPUS_ACCOUNTABILITY_ID
    schema_version: int = REGRESSION_CORPUS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise RegressionCorpusError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise RegressionCorpusError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "corpus_digest",
            _sha256(self.corpus_digest, "corpus_digest"),
        )
        object.__setattr__(
            self,
            "candidate_digest",
            _sha256(self.candidate_digest, "candidate_digest"),
        )
        object.__setattr__(
            self,
            "benchmark_qualification_digest",
            _sha256(
                self.benchmark_qualification_digest,
                "benchmark_qualification_digest",
            ),
        )
        for field in (
            "observation_digests",
            "risk_evaluation_digests",
            "passed_case_digests",
            "failed_case_digests",
        ):
            values = getattr(self, field)
            if not isinstance(values, tuple):
                raise RegressionCorpusError(f"{field} must be a tuple")
            normalized = tuple(sorted({_sha256(v, field) for v in values}))
            object.__setattr__(self, field, normalized)
        if self.task_id != REGRESSION_CORPUS_TASK_ID:
            raise RegressionCorpusError("task_id drift")
        if self.accountability_id != REGRESSION_CORPUS_ACCOUNTABILITY_ID:
            raise RegressionCorpusError("accountability_id drift")
        if self.schema_version != REGRESSION_CORPUS_SCHEMA_VERSION:
            raise RegressionCorpusError(
                "unsupported qualification schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "corpus_digest": self.corpus_digest,
            "candidate_digest": self.candidate_digest,
            "benchmark_qualification_digest": (
                self.benchmark_qualification_digest
            ),
            "observation_digests": list(self.observation_digests),
            "risk_evaluation_digests": list(
                self.risk_evaluation_digests
            ),
            "passed_case_digests": list(self.passed_case_digests),
            "failed_case_digests": list(self.failed_case_digests),
            "production_authority": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise RegressionCorpusError(
                "rejected regression corpus cannot become promotion evidence"
            )
        return EvidenceRef(
            source=(
                f"p1:learn-05:regressions:"
                f"{self.candidate_digest}"
            ),
            digest=self.decision_digest,
            category="regression_corpus_qualification",
        )


def _risk_digest(value: RiskBindingEvaluation) -> str:
    if not isinstance(value, RiskBindingEvaluation):
        raise TypeError(
            "risk evaluations must contain RiskBindingEvaluation"
        )
    return _canonical_digest(value.as_dict())


def qualify_regression_corpus(
    *,
    corpus: RegressionCorpus,
    candidate_digest: str,
    benchmark_qualification: BenchmarkQualificationDecision,
    expected_benchmark_qualification_digest: str,
    observations: Iterable[RegressionObservation],
    risk_evaluations: Mapping[str, RiskBindingEvaluation],
) -> RegressionQualificationDecision:
    if not isinstance(corpus, RegressionCorpus):
        raise TypeError("corpus must be RegressionCorpus")
    candidate = _sha256(candidate_digest, "candidate_digest")
    if not isinstance(
        benchmark_qualification,
        BenchmarkQualificationDecision,
    ):
        raise TypeError(
            "benchmark_qualification must be BenchmarkQualificationDecision"
        )
    expected_benchmark_digest = _sha256(
        expected_benchmark_qualification_digest,
        "expected_benchmark_qualification_digest",
    )
    if not isinstance(risk_evaluations, Mapping):
        raise TypeError("risk_evaluations must be a mapping")

    rows = tuple(observations)
    if any(not isinstance(item, RegressionObservation) for item in rows):
        raise TypeError(
            "observations must contain RegressionObservation"
        )

    reasons: list[str] = []
    benchmark_digest = benchmark_qualification.decision_digest
    if not benchmark_qualification.accepted:
        reasons.append("benchmark-qualification-rejected")
    if benchmark_digest != expected_benchmark_digest:
        reasons.append("benchmark-qualification-digest-mismatch")

    by_case: dict[str, list[RegressionObservation]] = {}
    for item in rows:
        by_case.setdefault(item.case_digest, []).append(item)
        if item.candidate_digest != candidate:
            reasons.append(
                f"candidate-digest-mismatch:{item.case_digest}"
            )

    passed: list[str] = []
    failed: list[str] = []
    risk_digests: list[str] = []

    known_case_digests = {item.case_digest for item in corpus.cases}
    unknown_observations = sorted(
        set(by_case) - known_case_digests
    )
    for digest in unknown_observations:
        reasons.append(f"unknown-regression-observation:{digest}")

    for case in corpus.cases:
        case_rows = by_case.get(case.case_digest, [])
        if not case_rows:
            reasons.append(f"regression-case-missing:{case.case_id}")
            failed.append(case.case_digest)
            continue
        if len(case_rows) != 1:
            reasons.append(
                f"regression-case-duplicate:{case.case_id}"
            )
            failed.append(case.case_digest)
            continue
        observation = case_rows[0]
        case_reasons: list[str] = []

        if observation.candidate_digest != candidate:
            case_reasons.append(
                f"candidate-digest-mismatch:{case.case_id}"
            )
        if observation.evaluator_id != case.evaluator_id:
            case_reasons.append(
                f"evaluator-id-mismatch:{case.case_id}"
            )
        if observation.evaluator_digest != case.evaluator_digest:
            case_reasons.append(
                f"evaluator-digest-mismatch:{case.case_id}"
            )
        if observation.actual_outcome is not case.expected_outcome:
            case_reasons.append(
                f"regression-reappeared:{case.case_id}:"
                f"expected-{case.expected_outcome.value}:"
                f"got-{observation.actual_outcome.value}"
            )

        risk = risk_evaluations.get(case.risk_obligation_id)
        if risk is None:
            case_reasons.append(
                f"risk-evaluation-missing:{case.case_id}"
            )
        else:
            if not isinstance(risk, RiskBindingEvaluation):
                raise TypeError(
                    "risk_evaluations values must be RiskBindingEvaluation"
                )
            risk_digests.append(_risk_digest(risk))
            if risk.obligation_id != case.risk_obligation_id:
                case_reasons.append(
                    f"risk-obligation-id-mismatch:{case.case_id}"
                )
            if risk.obligation_digest != case.risk_obligation_digest:
                case_reasons.append(
                    f"risk-obligation-digest-mismatch:{case.case_id}"
                )
            if not risk.resolved or risk.blockers:
                case_reasons.append(
                    f"risk-binding-unresolved:{case.case_id}"
                )
            if risk.blocking is not True:
                case_reasons.append(
                    f"risk-not-promotion-blocking:{case.case_id}"
                )

        reasons.extend(case_reasons)
        if case_reasons:
            failed.append(case.case_digest)
        else:
            passed.append(case.case_digest)

    normalized = tuple(sorted(set(reasons)))
    return RegressionQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        corpus_digest=corpus.corpus_digest,
        candidate_digest=candidate,
        benchmark_qualification_digest=benchmark_digest,
        observation_digests=tuple(
            item.observation_digest for item in rows
        ),
        risk_evaluation_digests=tuple(risk_digests),
        passed_case_digests=tuple(passed),
        failed_case_digests=tuple(failed),
    )


__all__ = [
    "REGRESSION_CORPUS_ACCOUNTABILITY_ID",
    "REGRESSION_CORPUS_SCHEMA_VERSION",
    "REGRESSION_CORPUS_TASK_ID",
    "FailureClass",
    "RegressionCase",
    "RegressionCorpus",
    "RegressionCorpusError",
    "RegressionObservation",
    "RegressionQualificationDecision",
    "SafeOutcome",
    "qualify_regression_corpus",
]
