"""P1 structured failure-knowledge pipeline.

Incidents, failed experiments, rejected designs, and counterexamples become
immutable knowledge records linked to EVID-04 risk identities and either exact
LEARN-05 regression coverage or an explicit independent non-applicability
decision. The pipeline emits learning signals only; it cannot mutate production,
candidate, champion, or maturity state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import CanonicalContractError, EvidenceRef, canonical_json_bytes
from skeleton.contracts.risk_evidence import RiskBindingEvaluation
from skeleton.eval.regression_corpus import FailureClass, RegressionCorpus


FAILURE_KNOWLEDGE_SCHEMA_VERSION = 1
FAILURE_KNOWLEDGE_TASK_ID = "P1-LEARN-06"
FAILURE_KNOWLEDGE_ACCOUNTABILITY_ID = "ACC-P1-LEARN-06"
_MAX_RECORDS = 4096
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,319}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FailureKnowledgeError(ValueError):
    """Failure-knowledge input violates lineage/isolation policy."""


class FailureSourceKind(str, Enum):
    INCIDENT = "incident"
    FAILED_EXPERIMENT = "failed_experiment"
    REJECTED_DESIGN = "rejected_design"
    COUNTEREXAMPLE = "counterexample"


class FailureDisposition(str, Enum):
    REGRESSION_COVERED = "regression_covered"
    NON_APPLICABLE = "non_applicable"


class LearningSignalKind(str, Enum):
    REGRESSION_REINFORCEMENT = "regression_reinforcement"
    NON_APPLICABILITY_REVIEW = "non_applicability_review"


def _token(value: object, field: str, *, maximum: int = 320) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise FailureKnowledgeError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FailureKnowledgeError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise FailureKnowledgeError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise FailureKnowledgeError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FailureKnowledgeError(f"{field} must be a positive integer")
    return value


def _canonical_digest(value: object) -> str:
    try:
        raw = canonical_json_bytes(value)
    except CanonicalContractError as exc:
        raise FailureKnowledgeError(
            "failure-knowledge payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _evidence(
    values: Iterable[EvidenceRef],
    field: str,
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise FailureKnowledgeError(
            f"{field} must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise FailureKnowledgeError(
                f"{field} must contain EvidenceRef values"
            )
        _text(item.source, f"{field}.source", maximum=2048)
        _sha256(item.digest, f"{field}.digest")
        _token(item.category, f"{field}.category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise FailureKnowledgeError(f"{field} must be non-empty")
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class NonApplicabilityDecision:
    failure_fingerprint: str
    risk_obligation_id: str
    risk_obligation_digest: str
    scope_digest: str
    reason: str
    reviewer_id: str
    reviewer_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    accepted: bool = True
    independent: bool = True

    def __post_init__(self) -> None:
        if self.accepted is not True:
            raise FailureKnowledgeError(
                "non-applicability decision must be accepted before use"
            )
        for field in (
            "failure_fingerprint",
            "risk_obligation_digest",
            "scope_digest",
            "reviewer_digest",
        ):
            object.__setattr__(
                self, field, _sha256(getattr(self, field), field)
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
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(
            self,
            "reviewer_id",
            _token(self.reviewer_id, "reviewer_id"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs, "evidence_refs"),
        )
        if self.independent is not True:
            raise FailureKnowledgeError(
                "non-applicability review must be independent"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "failure_fingerprint": self.failure_fingerprint,
            "risk_obligation_id": self.risk_obligation_id,
            "risk_obligation_digest": self.risk_obligation_digest,
            "scope_digest": self.scope_digest,
            "reason": self.reason,
            "reviewer_id": self.reviewer_id,
            "reviewer_digest": self.reviewer_digest,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
            "accepted": self.accepted,
            "independent": self.independent,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class FailureKnowledgeRecord:
    record_id: str
    version: int
    sequence: int
    source_kind: FailureSourceKind
    source_ref: str
    source_digest: str
    failure_class: FailureClass
    failure_fingerprint: str
    summary: str
    root_cause_digest: str
    risk_obligation_id: str
    risk_obligation_digest: str
    disposition: FailureDisposition
    evidence_refs: tuple[EvidenceRef, ...]
    regression_case_id: str | None = None
    regression_case_version: int | None = None
    regression_case_digest: str | None = None
    non_applicability: NonApplicabilityDecision | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "record_id", _token(self.record_id, "record_id")
        )
        object.__setattr__(
            self, "version", _positive_int(self.version, "version")
        )
        object.__setattr__(
            self, "sequence", _positive_int(self.sequence, "sequence")
        )
        try:
            object.__setattr__(
                self,
                "source_kind",
                FailureSourceKind(self.source_kind),
            )
            object.__setattr__(
                self,
                "failure_class",
                FailureClass(self.failure_class),
            )
            object.__setattr__(
                self,
                "disposition",
                FailureDisposition(self.disposition),
            )
        except ValueError as exc:
            raise FailureKnowledgeError(
                "invalid failure knowledge enum"
            ) from exc
        object.__setattr__(
            self, "source_ref", _token(self.source_ref, "source_ref")
        )
        for field in (
            "source_digest",
            "failure_fingerprint",
            "root_cause_digest",
            "risk_obligation_digest",
        ):
            object.__setattr__(
                self, field, _sha256(getattr(self, field), field)
            )
        object.__setattr__(self, "summary", _text(self.summary, "summary"))
        object.__setattr__(
            self,
            "risk_obligation_id",
            _token(
                self.risk_obligation_id,
                "risk_obligation_id",
                maximum=320,
            ),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs, "evidence_refs"),
        )

        if self.disposition is FailureDisposition.REGRESSION_COVERED:
            if (
                self.regression_case_id is None
                or self.regression_case_version is None
                or self.regression_case_digest is None
            ):
                raise FailureKnowledgeError(
                    "regression-covered record requires exact case identity"
                )
            object.__setattr__(
                self,
                "regression_case_id",
                _token(self.regression_case_id, "regression_case_id"),
            )
            object.__setattr__(
                self,
                "regression_case_version",
                _positive_int(
                    self.regression_case_version,
                    "regression_case_version",
                ),
            )
            object.__setattr__(
                self,
                "regression_case_digest",
                _sha256(
                    self.regression_case_digest,
                    "regression_case_digest",
                ),
            )
            if self.non_applicability is not None:
                raise FailureKnowledgeError(
                    "regression-covered record cannot be non-applicable"
                )
        else:
            if any(
                value is not None
                for value in (
                    self.regression_case_id,
                    self.regression_case_version,
                    self.regression_case_digest,
                )
            ):
                raise FailureKnowledgeError(
                    "non-applicable record cannot claim regression coverage"
                )
            if not isinstance(
                self.non_applicability,
                NonApplicabilityDecision,
            ):
                raise FailureKnowledgeError(
                    "non-applicable record requires independent decision"
                )
            if (
                self.non_applicability.failure_fingerprint
                != self.failure_fingerprint
            ):
                raise FailureKnowledgeError(
                    "non-applicability fingerprint mismatch"
                )
            if (
                self.non_applicability.risk_obligation_id
                != self.risk_obligation_id
                or self.non_applicability.risk_obligation_digest
                != self.risk_obligation_digest
            ):
                raise FailureKnowledgeError(
                    "non-applicability risk identity mismatch"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "version": self.version,
            "sequence": self.sequence,
            "source_kind": self.source_kind.value,
            "source_ref": self.source_ref,
            "source_digest": self.source_digest,
            "failure_class": self.failure_class.value,
            "failure_fingerprint": self.failure_fingerprint,
            "summary": self.summary,
            "root_cause_digest": self.root_cause_digest,
            "risk_obligation_id": self.risk_obligation_id,
            "risk_obligation_digest": self.risk_obligation_digest,
            "disposition": self.disposition.value,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
            "regression_case_id": self.regression_case_id,
            "regression_case_version": self.regression_case_version,
            "regression_case_digest": self.regression_case_digest,
            "non_applicability": (
                self.non_applicability.payload()
                if self.non_applicability is not None
                else None
            ),
        }

    @property
    def record_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class FailureKnowledgeLedger:
    ledger_id: str
    version: int
    records: tuple[FailureKnowledgeRecord, ...]
    parent_ledger_digest: str | None = None
    schema_version: int = FAILURE_KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "ledger_id", _token(self.ledger_id, "ledger_id")
        )
        object.__setattr__(
            self, "version", _positive_int(self.version, "version")
        )
        if (
            not isinstance(self.records, tuple)
            or not self.records
            or len(self.records) > _MAX_RECORDS
        ):
            raise FailureKnowledgeError(
                "records must be a bounded non-empty tuple"
            )
        if any(
            not isinstance(item, FailureKnowledgeRecord)
            for item in self.records
        ):
            raise FailureKnowledgeError(
                "records must contain FailureKnowledgeRecord"
            )
        sequences = [item.sequence for item in self.records]
        if sequences != list(range(1, len(self.records) + 1)):
            raise FailureKnowledgeError(
                "record sequence must be contiguous and ordered"
            )
        identities = [
            (item.record_id, item.version) for item in self.records
        ]
        if len(identities) != len(set(identities)):
            raise FailureKnowledgeError(
                "record id/version identities must be unique"
            )
        source_keys = [
            (item.source_kind.value, item.source_ref, item.source_digest)
            for item in self.records
        ]
        if len(source_keys) != len(set(source_keys)):
            raise FailureKnowledgeError(
                "failure source identities must be unique"
            )
        if self.parent_ledger_digest is not None:
            object.__setattr__(
                self,
                "parent_ledger_digest",
                _sha256(
                    self.parent_ledger_digest,
                    "parent_ledger_digest",
                ),
            )
        if self.schema_version != FAILURE_KNOWLEDGE_SCHEMA_VERSION:
            raise FailureKnowledgeError(
                "unsupported failure knowledge schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": FAILURE_KNOWLEDGE_TASK_ID,
            "accountability_id": FAILURE_KNOWLEDGE_ACCOUNTABILITY_ID,
            "ledger_id": self.ledger_id,
            "version": self.version,
            "records": [item.payload() for item in self.records],
            "parent_ledger_digest": self.parent_ledger_digest,
            "production_authority": False,
            "direct_self_modify": False,
        }

    @property
    def ledger_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class LearningSignal:
    record_digest: str
    failure_fingerprint: str
    risk_obligation_digest: str
    signal_kind: LearningSignalKind
    target_regression_case_digest: str | None
    non_applicability_digest: str | None
    production_authority: bool = False
    direct_self_modify: bool = False

    def __post_init__(self) -> None:
        for field in (
            "record_digest",
            "failure_fingerprint",
            "risk_obligation_digest",
        ):
            object.__setattr__(
                self, field, _sha256(getattr(self, field), field)
            )
        try:
            object.__setattr__(
                self,
                "signal_kind",
                LearningSignalKind(self.signal_kind),
            )
        except ValueError as exc:
            raise FailureKnowledgeError("invalid signal kind") from exc
        if self.target_regression_case_digest is not None:
            object.__setattr__(
                self,
                "target_regression_case_digest",
                _sha256(
                    self.target_regression_case_digest,
                    "target_regression_case_digest",
                ),
            )
        if self.non_applicability_digest is not None:
            object.__setattr__(
                self,
                "non_applicability_digest",
                _sha256(
                    self.non_applicability_digest,
                    "non_applicability_digest",
                ),
            )
        if self.production_authority is not False:
            raise FailureKnowledgeError(
                "learning signal cannot have production authority"
            )
        if self.direct_self_modify is not False:
            raise FailureKnowledgeError(
                "learning signal cannot directly self-modify"
            )
        if self.signal_kind is LearningSignalKind.REGRESSION_REINFORCEMENT:
            if (
                self.target_regression_case_digest is None
                or self.non_applicability_digest is not None
            ):
                raise FailureKnowledgeError(
                    "regression signal requires only regression case digest"
                )
        else:
            if (
                self.non_applicability_digest is None
                or self.target_regression_case_digest is not None
            ):
                raise FailureKnowledgeError(
                    "non-applicability signal requires only decision digest"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "record_digest": self.record_digest,
            "failure_fingerprint": self.failure_fingerprint,
            "risk_obligation_digest": self.risk_obligation_digest,
            "signal_kind": self.signal_kind.value,
            "target_regression_case_digest": (
                self.target_regression_case_digest
            ),
            "non_applicability_digest": self.non_applicability_digest,
            "production_authority": self.production_authority,
            "direct_self_modify": self.direct_self_modify,
        }

    @property
    def signal_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class FailureKnowledgeQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    ledger_digest: str
    regression_corpus_digest: str
    signal_digests: tuple[str, ...]
    task_id: str = FAILURE_KNOWLEDGE_TASK_ID
    accountability_id: str = FAILURE_KNOWLEDGE_ACCOUNTABILITY_ID
    schema_version: int = FAILURE_KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise FailureKnowledgeError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise FailureKnowledgeError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "ledger_digest",
            _sha256(self.ledger_digest, "ledger_digest"),
        )
        object.__setattr__(
            self,
            "regression_corpus_digest",
            _sha256(
                self.regression_corpus_digest,
                "regression_corpus_digest",
            ),
        )
        object.__setattr__(
            self,
            "signal_digests",
            tuple(sorted({_sha256(v, "signal_digests") for v in self.signal_digests})),
        )
        if self.task_id != FAILURE_KNOWLEDGE_TASK_ID:
            raise FailureKnowledgeError("task_id drift")
        if self.accountability_id != FAILURE_KNOWLEDGE_ACCOUNTABILITY_ID:
            raise FailureKnowledgeError("accountability_id drift")
        if self.schema_version != FAILURE_KNOWLEDGE_SCHEMA_VERSION:
            raise FailureKnowledgeError(
                "unsupported qualification schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "ledger_digest": self.ledger_digest,
            "regression_corpus_digest": self.regression_corpus_digest,
            "signal_digests": list(self.signal_digests),
            "production_authority": False,
            "direct_self_modify": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise FailureKnowledgeError(
                "rejected failure knowledge cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:learn-06:failure-knowledge:{self.ledger_digest}",
            digest=self.decision_digest,
            category="failure_knowledge_qualification",
        )


def learning_signal_for(record: FailureKnowledgeRecord) -> LearningSignal:
    if not isinstance(record, FailureKnowledgeRecord):
        raise TypeError("record must be FailureKnowledgeRecord")
    if record.disposition is FailureDisposition.REGRESSION_COVERED:
        return LearningSignal(
            record_digest=record.record_digest,
            failure_fingerprint=record.failure_fingerprint,
            risk_obligation_digest=record.risk_obligation_digest,
            signal_kind=LearningSignalKind.REGRESSION_REINFORCEMENT,
            target_regression_case_digest=record.regression_case_digest,
            non_applicability_digest=None,
        )
    assert record.non_applicability is not None
    return LearningSignal(
        record_digest=record.record_digest,
        failure_fingerprint=record.failure_fingerprint,
        risk_obligation_digest=record.risk_obligation_digest,
        signal_kind=LearningSignalKind.NON_APPLICABILITY_REVIEW,
        target_regression_case_digest=None,
        non_applicability_digest=record.non_applicability.decision_digest,
    )


def qualify_failure_knowledge(
    *,
    ledger: FailureKnowledgeLedger,
    regression_corpus: RegressionCorpus,
    risk_evaluations: Mapping[str, RiskBindingEvaluation],
) -> FailureKnowledgeQualificationDecision:
    if not isinstance(ledger, FailureKnowledgeLedger):
        raise TypeError("ledger must be FailureKnowledgeLedger")
    if not isinstance(regression_corpus, RegressionCorpus):
        raise TypeError("regression_corpus must be RegressionCorpus")
    if not isinstance(risk_evaluations, Mapping):
        raise TypeError("risk_evaluations must be a mapping")

    reasons: list[str] = []
    signals: list[LearningSignal] = []
    regression_by_key = {
        (case.case_id, case.version): case
        for case in regression_corpus.cases
    }

    seen_fingerprint_dispositions: dict[str, set[FailureDisposition]] = {}
    seen_fingerprint_targets: dict[str, set[str]] = {}
    for record in ledger.records:
        seen_fingerprint_dispositions.setdefault(
            record.failure_fingerprint,
            set(),
        ).add(record.disposition)

        if record.disposition is FailureDisposition.REGRESSION_COVERED:
            target_identity = f"regression:{record.regression_case_digest}"
        else:
            assert record.non_applicability is not None
            target_identity = (
                "non_applicability:"
                + record.non_applicability.decision_digest
            )
        seen_fingerprint_targets.setdefault(
            record.failure_fingerprint,
            set(),
        ).add(target_identity)

        risk = risk_evaluations.get(record.risk_obligation_id)
        if risk is None:
            reasons.append(
                f"risk-evaluation-missing:{record.record_id}"
            )
        else:
            if not isinstance(risk, RiskBindingEvaluation):
                raise TypeError(
                    "risk_evaluations values must be RiskBindingEvaluation"
                )
            if risk.obligation_id != record.risk_obligation_id:
                reasons.append(
                    f"risk-obligation-id-mismatch:{record.record_id}"
                )
            if risk.obligation_digest != record.risk_obligation_digest:
                reasons.append(
                    f"risk-obligation-digest-mismatch:{record.record_id}"
                )
            if not risk.resolved or risk.blockers:
                reasons.append(
                    f"risk-binding-unresolved:{record.record_id}"
                )
            if risk.blocking is not True:
                reasons.append(
                    f"risk-not-blocking:{record.record_id}"
                )

        if record.disposition is FailureDisposition.REGRESSION_COVERED:
            key = (
                record.regression_case_id,
                record.regression_case_version,
            )
            case = regression_by_key.get(key)
            if case is None:
                reasons.append(
                    f"regression-case-missing:{record.record_id}"
                )
            else:
                if case.case_digest != record.regression_case_digest:
                    reasons.append(
                        f"regression-case-digest-mismatch:{record.record_id}"
                    )
                if case.failure_class is not record.failure_class:
                    reasons.append(
                        f"failure-class-mismatch:{record.record_id}"
                    )
                if case.risk_obligation_id != record.risk_obligation_id:
                    reasons.append(
                        f"regression-risk-id-mismatch:{record.record_id}"
                    )
                if (
                    case.risk_obligation_digest
                    != record.risk_obligation_digest
                ):
                    reasons.append(
                        f"regression-risk-digest-mismatch:{record.record_id}"
                    )
        signals.append(learning_signal_for(record))

    for fingerprint, dispositions in seen_fingerprint_dispositions.items():
        if len(dispositions) > 1:
            reasons.append(
                f"failure-disposition-conflict:{fingerprint}"
            )
    for fingerprint, targets in seen_fingerprint_targets.items():
        if len(targets) > 1:
            reasons.append(
                f"failure-lineage-conflict:{fingerprint}"
            )

    normalized = tuple(sorted(set(reasons)))
    return FailureKnowledgeQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        ledger_digest=ledger.ledger_digest,
        regression_corpus_digest=regression_corpus.corpus_digest,
        signal_digests=tuple(item.signal_digest for item in signals),
    )


__all__ = [
    "FAILURE_KNOWLEDGE_ACCOUNTABILITY_ID",
    "FAILURE_KNOWLEDGE_SCHEMA_VERSION",
    "FAILURE_KNOWLEDGE_TASK_ID",
    "FailureDisposition",
    "FailureKnowledgeError",
    "FailureKnowledgeLedger",
    "FailureKnowledgeQualificationDecision",
    "FailureKnowledgeRecord",
    "FailureSourceKind",
    "LearningSignal",
    "LearningSignalKind",
    "NonApplicabilityDecision",
    "learning_signal_for",
    "qualify_failure_knowledge",
]
