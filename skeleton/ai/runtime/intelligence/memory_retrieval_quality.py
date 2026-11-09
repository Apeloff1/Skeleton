"""P1 memory, retrieval, and knowledge quality authority.

This module composes existing memory reconciliation, retrieval receipts/freshness,
canonical evidence references, and independent quality reports. It does not own
memory, retrieval indexes, or knowledge persistence and it never promotes state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef, evidence_ref_identity
from skeleton.intelligence.quality import QualityReport
from skeleton.memory.reconciliation import (
    MemoryAction,
    MemoryConflictResolution,
    MemoryConflictSet,
    MemoryDecision,
)
from skeleton.retrieval.freshness import PlaneFreshness
from skeleton.retrieval.receipts import RetrievalReceipt


INTEL_QUALITY_SCHEMA_VERSION = 1
INTEL_QUALITY_TASK_ID = "P1-INTEL-02"
INTEL_QUALITY_ACCOUNTABILITY_ID = "ACC-P1-INTEL-02"


class IntelligenceQualityError(ValueError):
    """Memory/retrieval/knowledge quality evidence is malformed."""


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IntelligenceQualityError(f"{field} must be finite numeric")
    number = float(value)
    if not math.isfinite(number):
        raise IntelligenceQualityError(f"{field} must be finite numeric")
    return number


def _sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise IntelligenceQualityError(f"{field} must be lowercase sha256")
    return value


def _text(value: object, field: str, *, max_length: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IntelligenceQualityError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > max_length:
        raise IntelligenceQualityError(f"{field} must be normalized")
    return normalized


def _evidence_refs(
    values: Iterable[EvidenceRef],
    field: str,
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise IntelligenceQualityError(f"{field} must contain EvidenceRef")
    normalized: dict[str, EvidenceRef] = {}
    for ref in values:
        if not isinstance(ref, EvidenceRef):
            raise IntelligenceQualityError(f"{field} must contain EvidenceRef")
        _text(ref.source, f"{field} source", max_length=2048)
        _sha256(ref.digest, f"{field} digest")
        _text(ref.category, f"{field} category", max_length=128)
        normalized[evidence_ref_identity(ref)] = ref
    if not normalized:
        raise IntelligenceQualityError(f"{field} requires evidence references")
    return tuple(normalized[key] for key in sorted(normalized))


def _evidence_payload(values: tuple[EvidenceRef, ...]) -> list[dict[str, str]]:
    return [
        {
            "identity": evidence_ref_identity(ref),
            "source": ref.source,
            "digest": ref.digest,
            "category": ref.category,
        }
        for ref in values
    ]


def _canonical_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class KnowledgeQualityObservation:
    """Provenance-bearing quality observation over one knowledge claim."""

    claim_id: str
    content_digest: str
    provenance_refs: tuple[EvidenceRef, ...]
    updated_at: float
    contradiction_count: int = 0
    superseded: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _text(self.claim_id, "claim_id"))
        object.__setattr__(
            self,
            "content_digest",
            _sha256(self.content_digest, "content_digest"),
        )
        updated = _finite(self.updated_at, "updated_at")
        if updated < 0:
            raise IntelligenceQualityError("updated_at must be non-negative")
        object.__setattr__(self, "updated_at", updated)
        if (
            isinstance(self.contradiction_count, bool)
            or not isinstance(self.contradiction_count, int)
            or self.contradiction_count < 0
        ):
            raise IntelligenceQualityError(
                "contradiction_count must be a non-negative integer"
            )
        if not isinstance(self.superseded, bool):
            raise IntelligenceQualityError("superseded must be boolean")
        if not isinstance(self.provenance_refs, tuple):
            raise IntelligenceQualityError(
                "knowledge claims require provenance references"
            )
        object.__setattr__(
            self,
            "provenance_refs",
            _evidence_refs(self.provenance_refs, "knowledge provenance"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "content_digest": self.content_digest,
            "updated_at": self.updated_at,
            "contradiction_count": self.contradiction_count,
            "superseded": self.superseded,
            "provenance_refs": _evidence_payload(self.provenance_refs),
        }


@dataclass(frozen=True, slots=True)
class IntelligenceQualityPolicy:
    min_memory_score: float = 0.45
    min_memory_freshness: float = 0.25
    min_memory_evidence: float = 0.10
    min_independent_quality_score: float = 0.70
    max_knowledge_age_s: float = 30.0 * 24.0 * 3600.0
    max_future_knowledge_skew_s: float = 300.0
    allow_partial_retrieval: bool = False
    require_retrieval_candidates: bool = True
    allow_memory_review: bool = False

    def __post_init__(self) -> None:
        for field in (
            "min_memory_score",
            "min_memory_freshness",
            "min_memory_evidence",
            "min_independent_quality_score",
        ):
            value = _finite(getattr(self, field), field)
            if not 0.0 <= value <= 1.0:
                raise IntelligenceQualityError(f"{field} must be in [0, 1]")
            object.__setattr__(self, field, value)
        max_age = _finite(self.max_knowledge_age_s, "max_knowledge_age_s")
        if max_age <= 0:
            raise IntelligenceQualityError(
                "max_knowledge_age_s must be positive"
            )
        object.__setattr__(self, "max_knowledge_age_s", max_age)
        future_skew = _finite(
            self.max_future_knowledge_skew_s,
            "max_future_knowledge_skew_s",
        )
        if future_skew < 0:
            raise IntelligenceQualityError(
                "max_future_knowledge_skew_s must be non-negative"
            )
        object.__setattr__(
            self,
            "max_future_knowledge_skew_s",
            future_skew,
        )
        for field in (
            "allow_partial_retrieval",
            "require_retrieval_candidates",
            "allow_memory_review",
        ):
            if not isinstance(getattr(self, field), bool):
                raise IntelligenceQualityError(f"{field} must be boolean")

    def payload(self) -> dict[str, Any]:
        return {
            "min_memory_score": self.min_memory_score,
            "min_memory_freshness": self.min_memory_freshness,
            "min_memory_evidence": self.min_memory_evidence,
            "min_independent_quality_score": self.min_independent_quality_score,
            "max_knowledge_age_s": self.max_knowledge_age_s,
            "max_future_knowledge_skew_s": self.max_future_knowledge_skew_s,
            "allow_partial_retrieval": self.allow_partial_retrieval,
            "require_retrieval_candidates": self.require_retrieval_candidates,
            "allow_memory_review": self.allow_memory_review,
        }


@dataclass(frozen=True, slots=True)
class IntelligenceQualityDecision:
    accepted: bool
    reasons: tuple[str, ...]
    memory_digest: str
    conflict_digest: str
    retrieval_digest: str
    retrieval_provenance_digest: str
    freshness_digest: str
    knowledge_digest: str
    quality_digest: str
    policy_digest: str
    observed_at: float
    task_id: str = INTEL_QUALITY_TASK_ID
    accountability_id: str = INTEL_QUALITY_ACCOUNTABILITY_ID
    schema_version: int = INTEL_QUALITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise IntelligenceQualityError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise IntelligenceQualityError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "memory_digest",
            "conflict_digest",
            "retrieval_digest",
            "retrieval_provenance_digest",
            "freshness_digest",
            "knowledge_digest",
            "quality_digest",
            "policy_digest",
        ):
            _sha256(getattr(self, field), field)
        object.__setattr__(
            self,
            "observed_at",
            _finite(self.observed_at, "observed_at"),
        )
        if self.task_id != INTEL_QUALITY_TASK_ID:
            raise IntelligenceQualityError("task_id drift")
        if self.accountability_id != INTEL_QUALITY_ACCOUNTABILITY_ID:
            raise IntelligenceQualityError("accountability_id drift")
        if self.schema_version != INTEL_QUALITY_SCHEMA_VERSION:
            raise IntelligenceQualityError("unsupported schema version")

    def identity_payload(self) -> dict[str, Any]:
        """State identity excluding wall-clock observation metadata."""
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "memory_digest": self.memory_digest,
            "conflict_digest": self.conflict_digest,
            "retrieval_digest": self.retrieval_digest,
            "retrieval_provenance_digest": self.retrieval_provenance_digest,
            "freshness_digest": self.freshness_digest,
            "knowledge_digest": self.knowledge_digest,
            "quality_digest": self.quality_digest,
            "policy_digest": self.policy_digest,
        }

    def payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "observed_at": self.observed_at,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.identity_payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:intel-02:memory-retrieval-knowledge-quality",
    ) -> EvidenceRef:
        if not self.accepted:
            raise IntelligenceQualityError(
                "rejected quality decision cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="intelligence_quality",
        )


def evaluate_intelligence_quality(
    *,
    memory_decisions: Iterable[MemoryDecision],
    memory_conflicts: Iterable[MemoryConflictSet],
    retrieval_receipt: RetrievalReceipt,
    retrieval_provenance: Iterable[EvidenceRef],
    freshness_by_plane: Mapping[str, PlaneFreshness],
    knowledge: Iterable[KnowledgeQualityObservation],
    quality_report: QualityReport,
    observed_at: float,
    policy: IntelligenceQualityPolicy | None = None,
) -> IntelligenceQualityDecision:
    """Evaluate one cross-plane intelligence-quality snapshot."""

    resolved_policy = policy or IntelligenceQualityPolicy()
    now = _finite(observed_at, "observed_at")
    if now < 0:
        raise IntelligenceQualityError("observed_at must be non-negative")
    if not isinstance(retrieval_receipt, RetrievalReceipt):
        raise TypeError("retrieval_receipt must be RetrievalReceipt")
    retrieval_evidence = _evidence_refs(
        retrieval_provenance,
        "retrieval provenance",
    )
    if not isinstance(quality_report, QualityReport):
        raise TypeError("quality_report must be QualityReport")
    if not isinstance(freshness_by_plane, Mapping):
        raise TypeError("freshness_by_plane must be a mapping")

    memories = tuple(sorted(tuple(memory_decisions), key=lambda row: row.record_id))
    if not memories or any(not isinstance(row, MemoryDecision) for row in memories):
        raise IntelligenceQualityError(
            "memory_decisions must contain MemoryDecision values"
        )
    if len({row.record_id for row in memories}) != len(memories):
        raise IntelligenceQualityError("memory_decisions contain duplicate record ids")

    conflicts = tuple(
        sorted(tuple(memory_conflicts), key=lambda row: row.conflict_id)
    )
    if any(not isinstance(row, MemoryConflictSet) for row in conflicts):
        raise IntelligenceQualityError(
            "memory_conflicts must contain MemoryConflictSet values"
        )
    if len({row.conflict_id for row in conflicts}) != len(conflicts):
        raise IntelligenceQualityError("memory_conflicts contain duplicate ids")

    knowledge_rows = tuple(
        sorted(tuple(knowledge), key=lambda row: row.claim_id)
    )
    if not knowledge_rows or any(
        not isinstance(row, KnowledgeQualityObservation)
        for row in knowledge_rows
    ):
        raise IntelligenceQualityError(
            "knowledge must contain KnowledgeQualityObservation values"
        )
    if len({row.claim_id for row in knowledge_rows}) != len(knowledge_rows):
        raise IntelligenceQualityError("knowledge contains duplicate claim ids")

    freshness_rows: dict[str, PlaneFreshness] = {}
    candidate_planes = set(retrieval_receipt.candidate_planes)
    for plane, row in freshness_by_plane.items():
        name = _text(plane, "freshness plane", max_length=128)
        if not isinstance(row, PlaneFreshness):
            raise IntelligenceQualityError(
                "freshness_by_plane values must be PlaneFreshness"
            )
        if row.plane != name:
            raise IntelligenceQualityError("freshness plane identity mismatch")
        if name in candidate_planes:
            freshness_rows[name] = row

    reasons: list[str] = []

    resolved_conflict_records: set[str] = set()
    superseded_conflict_records: set[str] = set()
    for conflict in conflicts:
        if conflict.resolution is MemoryConflictResolution.UNRESOLVED:
            reasons.append(f"memory-conflict-unresolved:{conflict.conflict_id}")
            continue
        candidate_ids = {row.record_id for row in conflict.candidates}
        if conflict.resolution is MemoryConflictResolution.KEEP_BOTH:
            resolved_conflict_records.update(candidate_ids)
        elif conflict.resolution is MemoryConflictResolution.SUPERSEDE:
            if conflict.winner_id is not None:
                resolved_conflict_records.add(conflict.winner_id)
            superseded_conflict_records.update(conflict.superseded_ids)

    for row in memories:
        score = _finite(row.score, f"memory score:{row.record_id}")
        if not 0.0 <= score <= 1.0:
            raise IntelligenceQualityError(
                f"memory score:{row.record_id} must be in [0, 1]"
            )
        if not isinstance(row.action, MemoryAction):
            raise IntelligenceQualityError(
                f"memory action:{row.record_id} must be MemoryAction"
            )
        if not isinstance(row.reasons, tuple) or any(
            not isinstance(reason, str) or not reason
            for reason in row.reasons
        ):
            raise IntelligenceQualityError(
                f"memory reasons:{row.record_id} are malformed"
            )
        if not isinstance(row.signals, tuple):
            raise IntelligenceQualityError(
                f"memory signals:{row.record_id} are malformed"
            )
        signals: dict[str, float] = {}
        for name, raw_value in row.signals:
            key = _text(name, f"memory signal name:{row.record_id}", max_length=64)
            if key in signals:
                raise IntelligenceQualityError(
                    f"memory signals:{row.record_id} contain duplicates"
                )
            value = _finite(
                raw_value,
                f"memory signal:{row.record_id}:{key}",
            )
            if not 0.0 <= value <= 1.0:
                raise IntelligenceQualityError(
                    f"memory signal:{row.record_id}:{key} must be in [0, 1]"
                )
            signals[key] = value
        required_signals = {"freshness", "utility", "evidence", "contradiction"}
        if set(signals) != required_signals:
            raise IntelligenceQualityError(
                f"memory signals:{row.record_id} must contain "
                "freshness, utility, evidence, contradiction"
            )

        if score < resolved_policy.min_memory_score:
            reasons.append(f"memory-quality-below-floor:{row.record_id}")
        if signals["freshness"] < resolved_policy.min_memory_freshness:
            reasons.append(f"memory-stale:{row.record_id}")
        if signals["evidence"] < resolved_policy.min_memory_evidence:
            reasons.append(f"memory-provenance-missing:{row.record_id}")
        if row.action is MemoryAction.TOMBSTONE:
            reasons.append(f"memory-tombstone:{row.record_id}")
        if (
            row.action is MemoryAction.REVIEW
            and not resolved_policy.allow_memory_review
        ):
            reasons.append(f"memory-review-required:{row.record_id}")
        if row.record_id in superseded_conflict_records:
            reasons.append(f"memory-conflict-superseded:{row.record_id}")
        if (
            signals["contradiction"] > 0.0
            or "contradicted" in row.reasons
        ) and row.record_id not in resolved_conflict_records:
            reasons.append(
                f"memory-contradiction-unresolved:{row.record_id}"
            )

    if retrieval_receipt.partial and not resolved_policy.allow_partial_retrieval:
        reasons.append("retrieval-partial")
    if retrieval_receipt.failed_planes:
        reasons.append("retrieval-plane-failure")
    if (
        resolved_policy.require_retrieval_candidates
        and not retrieval_receipt.candidate_planes
    ):
        reasons.append("retrieval-no-candidates")
    if not retrieval_receipt.fragment_ids:
        reasons.append("retrieval-no-fragments")

    for plane in retrieval_receipt.candidate_planes:
        freshness = freshness_rows.get(plane)
        if freshness is None:
            reasons.append(f"retrieval-freshness-missing:{plane}")
            continue
        if freshness.stale(now):
            reasons.append(f"retrieval-stale:{plane}")
        if not freshness.source_revision:
            reasons.append(f"retrieval-source-revision-missing:{plane}")

    for row in knowledge_rows:
        future_skew = row.updated_at - now
        if future_skew > resolved_policy.max_future_knowledge_skew_s:
            reasons.append(f"knowledge-future-dated:{row.claim_id}")
        age = max(0.0, now - row.updated_at)
        if age > resolved_policy.max_knowledge_age_s:
            reasons.append(f"knowledge-stale:{row.claim_id}")
        if row.contradiction_count:
            reasons.append(f"knowledge-contradicted:{row.claim_id}")
        if row.superseded:
            reasons.append(f"knowledge-superseded:{row.claim_id}")

    if not isinstance(quality_report.accepted, bool):
        raise IntelligenceQualityError(
            "quality_report.accepted must be boolean"
        )
    quality_score = _finite(quality_report.score, "quality_report.score")
    if not 0.0 <= quality_score <= 1.0:
        raise IntelligenceQualityError(
            "quality_report.score must be in [0, 1]"
        )
    if not quality_report.accepted:
        reasons.append("independent-quality-rejected")
    if quality_score < resolved_policy.min_independent_quality_score:
        reasons.append("independent-quality-below-floor")

    memory_payload = [row.to_dict() for row in memories]
    conflict_payload = [
        {
            "conflict_id": row.conflict_id,
            "scope_key": row.scope_key,
            "claim_key": row.claim_key,
            "resolution": row.resolution.value,
            "winner_id": row.winner_id,
            "superseded_ids": list(row.superseded_ids),
            "reason": row.reason,
            "candidates": [candidate.to_dict() for candidate in row.candidates],
        }
        for row in conflicts
    ]
    freshness_payload = {
        key: {
            **row.to_dict(),
            "stale": row.stale(now),
        }
        for key, row in sorted(freshness_rows.items())
    }
    knowledge_payload = [row.payload() for row in knowledge_rows]

    return IntelligenceQualityDecision(
        accepted=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        memory_digest=_canonical_digest(memory_payload),
        conflict_digest=_canonical_digest(conflict_payload),
        retrieval_digest=_canonical_digest(retrieval_receipt.to_dict()),
        retrieval_provenance_digest=_canonical_digest(
            _evidence_payload(retrieval_evidence)
        ),
        freshness_digest=_canonical_digest(freshness_payload),
        knowledge_digest=_canonical_digest(knowledge_payload),
        quality_digest=_canonical_digest(quality_report.to_dict()),
        policy_digest=_canonical_digest(resolved_policy.payload()),
        observed_at=now,
    )


__all__ = [
    "INTEL_QUALITY_ACCOUNTABILITY_ID",
    "INTEL_QUALITY_SCHEMA_VERSION",
    "INTEL_QUALITY_TASK_ID",
    "IntelligenceQualityDecision",
    "IntelligenceQualityError",
    "IntelligenceQualityPolicy",
    "KnowledgeQualityObservation",
    "evaluate_intelligence_quality",
]
