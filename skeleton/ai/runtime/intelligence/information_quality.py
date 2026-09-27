"""Joined memory, retrieval, and knowledge quality authority for P1.

This module does not own memory, retrieval, or knowledge storage. It joins the
canonical quality and lineage decisions already emitted by those subsystems and
turns them into one fail-closed, deterministic receipt suitable for P1 evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef
from skeleton.frontier.contracts import stable_content_digest
from skeleton.intelligence.knowledge_base import Document
from skeleton.memory.reconciliation import (
    MemoryAction,
    MemoryConflictResolution,
    MemoryConflictSet,
    MemoryDecision,
)
from skeleton.retrieval.freshness import PlaneFreshness
from skeleton.retrieval.receipts import RetrievalReceipt


INFORMATION_QUALITY_SCHEMA_VERSION = 1
INFORMATION_QUALITY_TASK_ID = "P1-INTEL-02"
INFORMATION_QUALITY_ACCOUNTABILITY_ID = "ACC-P1-INTEL-02"


class InformationQualityError(ValueError):
    """Memory/retrieval/knowledge evidence cannot be joined safely."""


def _text(value: object, field: str, *, max_length: int = 2048) -> str:
    if not isinstance(value, str) or not value:
        raise InformationQualityError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise InformationQualityError(f"{field} must be normalized")
    if len(value) > max_length:
        raise InformationQualityError(f"{field} exceeds maximum length")
    return value


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, max_length=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise InformationQualityError(f"{field} must be lowercase sha256")
    return text


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InformationQualityError(
            f"{field} must be a non-negative integer"
        )
    return value


def _positive_int(value: object, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value < 1:
        raise InformationQualityError(f"{field} must be positive")
    return value


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InformationQualityError(f"{field} must be finite and non-negative")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise InformationQualityError(f"{field} must be finite and non-negative")
    return number


def _string_tuple(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise InformationQualityError(f"{field} must be an iterable")
    result: list[str] = []
    for raw in values:
        item = _text(raw, field)
        if item not in result:
            result.append(item)
    if not allow_empty and not result:
        raise InformationQualityError(f"{field} must not be empty")
    return tuple(sorted(result))


def _document_digest(document: Document) -> str:
    if not isinstance(document, Document):
        raise TypeError("document must be Document")
    return hashlib.sha256(document.body.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class KnowledgeObservation:
    """Provenance/freshness wrapper around one versioned knowledge document."""

    document_id: str
    version: int
    content_digest: str
    source_revision: str
    provenance_refs: tuple[str, ...]
    updated_ns: int
    stale_after_ns: int
    contradiction_count: int = 0
    contradiction_resolution_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "document_id",
            _text(self.document_id, "document_id", max_length=256),
        )
        object.__setattr__(self, "version", _positive_int(self.version, "version"))
        object.__setattr__(
            self,
            "content_digest",
            _sha256(self.content_digest, "content_digest"),
        )
        object.__setattr__(
            self,
            "source_revision",
            _text(self.source_revision, "source_revision", max_length=512),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _string_tuple(
                self.provenance_refs,
                "provenance_refs",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "updated_ns",
            _nonnegative_int(self.updated_ns, "updated_ns"),
        )
        object.__setattr__(
            self,
            "stale_after_ns",
            _positive_int(self.stale_after_ns, "stale_after_ns"),
        )
        object.__setattr__(
            self,
            "contradiction_count",
            _nonnegative_int(self.contradiction_count, "contradiction_count"),
        )
        object.__setattr__(
            self,
            "contradiction_resolution_refs",
            _string_tuple(
                self.contradiction_resolution_refs,
                "contradiction_resolution_refs",
            ),
        )

    def stale(self, *, now_ns: int) -> bool:
        resolved = _nonnegative_int(now_ns, "now_ns")
        return resolved >= self.updated_ns + self.stale_after_ns

    def identity_dict(self, *, now_ns: int) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "version": self.version,
            "content_digest": self.content_digest,
            "source_revision": self.source_revision,
            "provenance_refs": list(self.provenance_refs),
            "stale": self.stale(now_ns=now_ns),
            "contradiction_count": self.contradiction_count,
            "contradiction_resolution_refs": list(
                self.contradiction_resolution_refs
            ),
        }


def observe_knowledge_document(
    document: Document,
    *,
    source_revision: str,
    provenance_refs: Iterable[str],
    stale_after_ns: int,
    contradiction_count: int = 0,
    contradiction_resolution_refs: Iterable[str] = (),
) -> KnowledgeObservation:
    """Bind a mutable store document to explicit lineage without changing it."""

    if not isinstance(document, Document):
        raise TypeError("document must be Document")
    return KnowledgeObservation(
        document_id=document.doc_id,
        version=document.version,
        content_digest=_document_digest(document),
        source_revision=source_revision,
        provenance_refs=tuple(provenance_refs),
        updated_ns=document.updated_ns,
        stale_after_ns=stale_after_ns,
        contradiction_count=contradiction_count,
        contradiction_resolution_refs=tuple(contradiction_resolution_refs),
    )


@dataclass(frozen=True, slots=True)
class InformationQualityPolicy:
    """Fail-closed policy over information inputs actually used by a task."""

    require_scoped_retrieval: bool = True
    allow_partial_retrieval: bool = False
    allow_failed_retrieval_planes: bool = False
    allow_stale_retrieval_planes: bool = False
    require_all_retrieval_freshness: bool = True
    require_memory_retain: bool = True
    block_unresolved_memory_conflicts: bool = True
    allow_stale_knowledge: bool = False
    allow_unresolved_knowledge_contradictions: bool = False

    def __post_init__(self) -> None:
        for field in (
            "require_scoped_retrieval",
            "allow_partial_retrieval",
            "allow_failed_retrieval_planes",
            "allow_stale_retrieval_planes",
            "require_all_retrieval_freshness",
            "require_memory_retain",
            "block_unresolved_memory_conflicts",
            "allow_stale_knowledge",
            "allow_unresolved_knowledge_contradictions",
        ):
            if not isinstance(getattr(self, field), bool):
                raise InformationQualityError(f"{field} must be boolean")

    @property
    def digest(self) -> str:
        return stable_content_digest(self.as_dict())

    def as_dict(self) -> dict[str, bool]:
        return {
            field: getattr(self, field)
            for field in (
                "require_scoped_retrieval",
                "allow_partial_retrieval",
                "allow_failed_retrieval_planes",
                "allow_stale_retrieval_planes",
                "require_all_retrieval_freshness",
                "require_memory_retain",
                "block_unresolved_memory_conflicts",
                "allow_stale_knowledge",
                "allow_unresolved_knowledge_contradictions",
            )
        }


@dataclass(frozen=True, slots=True)
class InformationQualityReceipt:
    """Deterministic joined authority for memory/retrieval/knowledge quality."""

    policy_digest: str
    memory_digest: str
    retrieval_digest: str
    knowledge_digest: str
    memory_record_ids: tuple[str, ...]
    unresolved_memory_conflict_ids: tuple[str, ...]
    retrieval_receipt_id: str | None
    retrieval_scope_digest: str | None
    stale_retrieval_planes: tuple[str, ...]
    missing_retrieval_freshness: tuple[str, ...]
    knowledge_document_ids: tuple[str, ...]
    stale_knowledge_document_ids: tuple[str, ...]
    unresolved_knowledge_document_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    eligible_for_promotion: bool
    task_id: str = INFORMATION_QUALITY_TASK_ID
    accountability_id: str = INFORMATION_QUALITY_ACCOUNTABILITY_ID
    schema_version: int = INFORMATION_QUALITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INFORMATION_QUALITY_SCHEMA_VERSION:
            raise InformationQualityError("unsupported receipt schema version")
        if self.task_id != INFORMATION_QUALITY_TASK_ID:
            raise InformationQualityError("task_id drift")
        if self.accountability_id != INFORMATION_QUALITY_ACCOUNTABILITY_ID:
            raise InformationQualityError("accountability_id drift")
        for field in (
            "policy_digest",
            "memory_digest",
            "retrieval_digest",
            "knowledge_digest",
        ):
            _sha256(getattr(self, field), field)
        if self.eligible_for_promotion != (not self.blockers):
            raise InformationQualityError(
                "promotion eligibility must be derived from blockers"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "policy_digest": self.policy_digest,
            "memory_digest": self.memory_digest,
            "retrieval_digest": self.retrieval_digest,
            "knowledge_digest": self.knowledge_digest,
            "memory_record_ids": list(self.memory_record_ids),
            "unresolved_memory_conflict_ids": list(
                self.unresolved_memory_conflict_ids
            ),
            "retrieval_receipt_id": self.retrieval_receipt_id,
            "retrieval_scope_digest": self.retrieval_scope_digest,
            "stale_retrieval_planes": list(self.stale_retrieval_planes),
            "missing_retrieval_freshness": list(
                self.missing_retrieval_freshness
            ),
            "knowledge_document_ids": list(self.knowledge_document_ids),
            "stale_knowledge_document_ids": list(
                self.stale_knowledge_document_ids
            ),
            "unresolved_knowledge_document_ids": list(
                self.unresolved_knowledge_document_ids
            ),
            "blockers": list(self.blockers),
            "eligible_for_promotion": self.eligible_for_promotion,
        }

    @property
    def receipt_digest(self) -> str:
        return stable_content_digest(self.identity_payload())

    def payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "receipt_digest": self.receipt_digest,
        }

    def evidence_ref(self) -> EvidenceRef:
        if not self.eligible_for_promotion:
            raise InformationQualityError(
                "blocked information-quality receipt cannot become promotion evidence"
            )
        return EvidenceRef(
            source="p1:memory-retrieval-knowledge-quality",
            digest=self.receipt_digest,
            category="information_quality",
        )


def _memory_state(
    decisions: Iterable[MemoryDecision],
    conflicts: Iterable[MemoryConflictSet],
    *,
    policy: InformationQualityPolicy,
) -> tuple[str, tuple[str, ...], tuple[str, ...], list[str]]:
    decision_rows = tuple(
        sorted(tuple(decisions), key=lambda row: row.record_id)
    )
    if any(not isinstance(row, MemoryDecision) for row in decision_rows):
        raise TypeError("memory decisions must contain MemoryDecision values")
    ids = tuple(row.record_id for row in decision_rows)
    if len(ids) != len(set(ids)):
        raise InformationQualityError("memory decision record ids must be unique")

    conflict_rows = tuple(
        sorted(tuple(conflicts), key=lambda row: row.conflict_id)
    )
    if any(not isinstance(row, MemoryConflictSet) for row in conflict_rows):
        raise TypeError("memory conflicts must contain MemoryConflictSet values")
    conflict_ids = tuple(row.conflict_id for row in conflict_rows)
    if len(conflict_ids) != len(set(conflict_ids)):
        raise InformationQualityError("memory conflict ids must be unique")

    unresolved = tuple(
        row.conflict_id
        for row in conflict_rows
        if row.resolution is MemoryConflictResolution.UNRESOLVED
    )
    blockers: list[str] = []
    if policy.require_memory_retain and any(
        row.action is not MemoryAction.RETAIN for row in decision_rows
    ):
        blockers.append("memory_not_retained")
    if policy.block_unresolved_memory_conflicts and unresolved:
        blockers.append("unresolved_memory_conflict")

    digest = stable_content_digest(
        {
            "decisions": [row.to_dict() for row in decision_rows],
            "conflicts": [row.to_dict() for row in conflict_rows],
        }
    )
    return digest, ids, unresolved, blockers


def _retrieval_state(
    receipt: RetrievalReceipt | None,
    freshness: Mapping[str, PlaneFreshness],
    *,
    now: float,
    policy: InformationQualityPolicy,
) -> tuple[
    str,
    str | None,
    str | None,
    tuple[str, ...],
    tuple[str, ...],
    list[str],
]:
    now_value = _finite_nonnegative(now, "now")
    if not isinstance(freshness, Mapping):
        raise TypeError("freshness must be a mapping")
    for plane, state in freshness.items():
        if not isinstance(plane, str) or not plane:
            raise InformationQualityError("freshness plane names must be non-empty")
        if not isinstance(state, PlaneFreshness):
            raise TypeError("freshness values must be PlaneFreshness")
        if state.plane != plane:
            raise InformationQualityError("freshness mapping key/plane mismatch")

    if receipt is None:
        return (
            stable_content_digest({"receipt": None, "freshness": []}),
            None,
            None,
            (),
            (),
            [],
        )
    if not isinstance(receipt, RetrievalReceipt):
        raise TypeError("retrieval receipt must be RetrievalReceipt or None")

    considered = tuple(sorted(receipt.considered_planes))
    missing = tuple(sorted(set(considered) - set(freshness)))
    stale = tuple(
        sorted(
            plane
            for plane in considered
            if plane in freshness and freshness[plane].stale(now_value)
        )
    )
    blockers: list[str] = []
    if policy.require_scoped_retrieval and not receipt.scope_digest:
        blockers.append("retrieval_scope_missing")
    if not policy.allow_partial_retrieval and receipt.partial:
        blockers.append("retrieval_partial")
    if not policy.allow_failed_retrieval_planes and receipt.failed_planes:
        blockers.append("retrieval_plane_failed")
    if policy.require_all_retrieval_freshness and missing:
        blockers.append("retrieval_freshness_missing")
    if not policy.allow_stale_retrieval_planes and stale:
        blockers.append("retrieval_plane_stale")

    freshness_identity = [
        {
            "plane": plane,
            "index_version": freshness[plane].index_version,
            "source_revision": freshness[plane].source_revision,
            "stale": freshness[plane].stale(now_value),
        }
        for plane in considered
        if plane in freshness
    ]
    digest = stable_content_digest(
        {
            "receipt": receipt.to_dict(),
            "freshness": freshness_identity,
        }
    )
    return (
        digest,
        receipt.receipt_id,
        receipt.scope_digest,
        stale,
        missing,
        blockers,
    )


def _knowledge_state(
    observations: Iterable[KnowledgeObservation],
    *,
    now_ns: int,
    policy: InformationQualityPolicy,
) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], list[str]]:
    now_value = _nonnegative_int(now_ns, "now_ns")
    rows = tuple(
        sorted(tuple(observations), key=lambda row: row.document_id)
    )
    if any(not isinstance(row, KnowledgeObservation) for row in rows):
        raise TypeError(
            "knowledge observations must contain KnowledgeObservation values"
        )
    ids = tuple(row.document_id for row in rows)
    if len(ids) != len(set(ids)):
        raise InformationQualityError(
            "knowledge document ids must be unique"
        )

    stale = tuple(row.document_id for row in rows if row.stale(now_ns=now_value))
    unresolved = tuple(
        row.document_id
        for row in rows
        if row.contradiction_count > 0 and not row.contradiction_resolution_refs
    )
    blockers: list[str] = []
    if not policy.allow_stale_knowledge and stale:
        blockers.append("knowledge_stale")
    if not policy.allow_unresolved_knowledge_contradictions and unresolved:
        blockers.append("knowledge_contradiction_unresolved")

    digest = stable_content_digest(
        {
            "observations": [
                row.identity_dict(now_ns=now_value) for row in rows
            ]
        }
    )
    return digest, ids, stale, unresolved, blockers


def build_information_quality_receipt(
    *,
    memory_decisions: Iterable[MemoryDecision] = (),
    memory_conflicts: Iterable[MemoryConflictSet] = (),
    retrieval_receipt: RetrievalReceipt | None = None,
    retrieval_freshness: Mapping[str, PlaneFreshness] | None = None,
    knowledge_observations: Iterable[KnowledgeObservation] = (),
    now: float,
    now_ns: int,
    policy: InformationQualityPolicy | None = None,
) -> InformationQualityReceipt:
    """Join information-plane quality without mutating any source authority."""

    resolved_policy = policy or InformationQualityPolicy()
    memory_digest, memory_ids, unresolved_memory, memory_blockers = (
        _memory_state(
            memory_decisions,
            memory_conflicts,
            policy=resolved_policy,
        )
    )
    (
        retrieval_digest,
        retrieval_id,
        retrieval_scope,
        stale_planes,
        missing_freshness,
        retrieval_blockers,
    ) = _retrieval_state(
        retrieval_receipt,
        {} if retrieval_freshness is None else retrieval_freshness,
        now=now,
        policy=resolved_policy,
    )
    (
        knowledge_digest,
        knowledge_ids,
        stale_knowledge,
        unresolved_knowledge,
        knowledge_blockers,
    ) = _knowledge_state(
        knowledge_observations,
        now_ns=now_ns,
        policy=resolved_policy,
    )
    blockers = tuple(
        sorted(
            set(
                memory_blockers
                + retrieval_blockers
                + knowledge_blockers
            )
        )
    )
    return InformationQualityReceipt(
        policy_digest=resolved_policy.digest,
        memory_digest=memory_digest,
        retrieval_digest=retrieval_digest,
        knowledge_digest=knowledge_digest,
        memory_record_ids=memory_ids,
        unresolved_memory_conflict_ids=unresolved_memory,
        retrieval_receipt_id=retrieval_id,
        retrieval_scope_digest=retrieval_scope,
        stale_retrieval_planes=stale_planes,
        missing_retrieval_freshness=missing_freshness,
        knowledge_document_ids=knowledge_ids,
        stale_knowledge_document_ids=stale_knowledge,
        unresolved_knowledge_document_ids=unresolved_knowledge,
        blockers=blockers,
        eligible_for_promotion=not blockers,
    )


__all__ = [
    "INFORMATION_QUALITY_ACCOUNTABILITY_ID",
    "INFORMATION_QUALITY_SCHEMA_VERSION",
    "INFORMATION_QUALITY_TASK_ID",
    "InformationQualityError",
    "InformationQualityPolicy",
    "InformationQualityReceipt",
    "KnowledgeObservation",
    "build_information_quality_receipt",
    "observe_knowledge_document",
]
