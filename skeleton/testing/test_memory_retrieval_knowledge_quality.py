from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.memory_retrieval_quality import (
    IntelligenceQualityError,
    IntelligenceQualityPolicy,
    KnowledgeQualityObservation,
    evaluate_intelligence_quality,
)
from skeleton.intelligence.quality import QualityReport
from skeleton.memory.reconciliation import (
    MemoryAction,
    MemoryConflictCandidate,
    MemoryConflictResolution,
    MemoryConflictSet,
    MemoryDecision,
)
from skeleton.retrieval.freshness import PlaneFreshness
from skeleton.retrieval.receipts import RetrievalReceipt


NOW = 1_800_000_000.0


def _memory(
    *,
    record_id: str = "memory-1",
    action: MemoryAction = MemoryAction.RETAIN,
    score: float = 0.90,
) -> MemoryDecision:
    return MemoryDecision(
        record_id=record_id,
        action=action,
        score=score,
        reasons=(),
        signals=(
            ("freshness", 0.95),
            ("utility", 0.80),
            ("evidence", 0.90),
            ("contradiction", 0.0),
        ),
    )


def _retrieval(
    *,
    partial: bool = False,
    candidate_planes: tuple[str, ...] = ("lexical",),
    failed_planes: tuple[str, ...] = (),
    fragment_planes: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
) -> RetrievalReceipt:
    fragments = (
        (("fragment-1", candidate_planes),)
        if fragment_planes is None and candidate_planes
        else (() if fragment_planes is None else fragment_planes)
    )
    considered = tuple(dict.fromkeys((*candidate_planes, *failed_planes)))
    return RetrievalReceipt(
        receipt_id="receipt-1",
        query_digest="query-digest",
        generation=4,
        scope_digest="scope-digest",
        considered_planes=considered,
        candidate_planes=candidate_planes,
        failed_planes=failed_planes,
        fragment_planes=fragments,
        partial=partial,
        created_ns=1,
        source="live",
    )


def _fresh(
    plane: str = "lexical",
    *,
    indexed_at: float = NOW - 100.0,
    stale_after_s: float = 1000.0,
    source_revision: str = "rev-7",
) -> PlaneFreshness:
    return PlaneFreshness(
        plane=plane,
        index_version="index-v7",
        source_revision=source_revision,
        indexed_at=indexed_at,
        stale_after_s=stale_after_s,
    )


def _knowledge(
    *,
    claim_id: str = "claim-1",
    updated_at: float = NOW - 100.0,
    contradiction_count: int = 0,
    superseded: bool = False,
    refs: tuple[EvidenceRef, ...] | None = None,
) -> KnowledgeQualityObservation:
    evidence = refs or (
        EvidenceRef(
            source="knowledge://claim-1/source-a",
            digest="a" * 64,
            category="knowledge_source",
        ),
    )
    return KnowledgeQualityObservation(
        claim_id=claim_id,
        content_digest="b" * 64,
        provenance_refs=evidence,
        updated_at=updated_at,
        contradiction_count=contradiction_count,
        superseded=superseded,
    )


def _quality(
    *,
    accepted: bool = True,
    score: float = 0.92,
) -> QualityReport:
    return QualityReport(
        accepted=accepted,
        reason="independent quality evaluation",
        score=score,
    )


def _evaluate(**overrides):
    values = {
        "memory_decisions": (_memory(),),
        "memory_conflicts": (),
        "retrieval_receipt": _retrieval(),
        "freshness_by_plane": {"lexical": _fresh()},
        "knowledge": (_knowledge(),),
        "quality_report": _quality(),
        "observed_at": NOW,
    }
    values.update(overrides)
    return evaluate_intelligence_quality(**values)


def _unresolved_conflict() -> MemoryConflictSet:
    candidates = (
        MemoryConflictCandidate(
            record_id="memory-a",
            scope_key="tenant-a/project-a",
            claim_key="claim-x",
            payload_digest="1" * 64,
            confidence=0.80,
            provenance_count=2,
            updated_at=NOW - 20.0,
        ),
        MemoryConflictCandidate(
            record_id="memory-b",
            scope_key="tenant-a/project-a",
            claim_key="claim-x",
            payload_digest="2" * 64,
            confidence=0.75,
            provenance_count=2,
            updated_at=NOW - 10.0,
        ),
    )
    return MemoryConflictSet(
        conflict_id="conflict-1",
        scope_key="tenant-a/project-a",
        claim_key="claim-x",
        candidates=candidates,
        created_at=NOW - 5.0,
    )


def test_quality_authority_accepts_fresh_provenanced_consistent_snapshot() -> None:
    decision = _evaluate()

    assert decision.accepted is True
    assert decision.reasons == ()
    assert len(decision.decision_digest) == 64
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "intelligence_quality"
    assert evidence.digest == decision.decision_digest


@pytest.mark.parametrize(
    ("memory", "reason"),
    (
        (_memory(score=0.40), "memory-quality-below-floor:memory-1"),
        (
            _memory(action=MemoryAction.REVIEW),
            "memory-review-required:memory-1",
        ),
        (
            _memory(action=MemoryAction.TOMBSTONE),
            "memory-tombstone:memory-1",
        ),
    ),
)
def test_memory_quality_failures_reject(
    memory: MemoryDecision,
    reason: str,
) -> None:
    decision = _evaluate(memory_decisions=(memory,))

    assert decision.accepted is False
    assert reason in decision.reasons


def test_unresolved_memory_conflict_rejects() -> None:
    conflict = _unresolved_conflict()

    decision = _evaluate(memory_conflicts=(conflict,))

    assert decision.accepted is False
    assert "memory-conflict-unresolved:conflict-1" in decision.reasons


@pytest.mark.parametrize(
    ("receipt", "reason"),
    (
        (_retrieval(partial=True), "retrieval-partial"),
        (
            _retrieval(
                candidate_planes=("lexical",),
                failed_planes=("dense",),
            ),
            "retrieval-plane-failure",
        ),
        (
            _retrieval(candidate_planes=()),
            "retrieval-no-candidates",
        ),
        (
            _retrieval(fragment_planes=()),
            "retrieval-no-fragments",
        ),
    ),
)
def test_retrieval_quality_failures_reject(
    receipt: RetrievalReceipt,
    reason: str,
) -> None:
    freshness = {
        plane: _fresh(plane)
        for plane in receipt.candidate_planes
    }
    decision = _evaluate(
        retrieval_receipt=receipt,
        freshness_by_plane=freshness,
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_missing_or_stale_candidate_freshness_rejects() -> None:
    missing = _evaluate(freshness_by_plane={})
    assert missing.accepted is False
    assert "retrieval-freshness-missing:lexical" in missing.reasons

    stale = _evaluate(
        freshness_by_plane={
            "lexical": _fresh(
                indexed_at=NOW - 2000.0,
                stale_after_s=1000.0,
            )
        }
    )
    assert stale.accepted is False
    assert "retrieval-stale:lexical" in stale.reasons


def test_irrelevant_freshness_does_not_change_identity() -> None:
    baseline = _evaluate()
    with_extra = _evaluate(
        freshness_by_plane={
            "lexical": _fresh(),
            "unused": _fresh("unused"),
        }
    )

    assert with_extra.accepted is True
    assert with_extra.freshness_digest == baseline.freshness_digest
    assert with_extra.decision_digest == baseline.decision_digest


@pytest.mark.parametrize(
    ("knowledge", "reason"),
    (
        (
            _knowledge(updated_at=NOW - 40.0 * 24.0 * 3600.0),
            "knowledge-stale:claim-1",
        ),
        (
            _knowledge(contradiction_count=1),
            "knowledge-contradicted:claim-1",
        ),
        (
            _knowledge(superseded=True),
            "knowledge-superseded:claim-1",
        ),
    ),
)
def test_knowledge_quality_failures_reject(
    knowledge: KnowledgeQualityObservation,
    reason: str,
) -> None:
    decision = _evaluate(knowledge=(knowledge,))

    assert decision.accepted is False
    assert reason in decision.reasons


def test_knowledge_requires_real_provenance() -> None:
    with pytest.raises(
        IntelligenceQualityError,
        match="require provenance references",
    ):
        KnowledgeQualityObservation(
            claim_id="claim-1",
            content_digest="b" * 64,
            provenance_refs=(),
            updated_at=NOW,
        )

    with pytest.raises(IntelligenceQualityError, match="provenance digest"):
        _knowledge(
            refs=(
                EvidenceRef(
                    source="knowledge://bad",
                    digest="bad",
                    category="knowledge_source",
                ),
            )
        )


def test_provenance_order_and_duplicates_are_canonical() -> None:
    left = EvidenceRef(
        source="knowledge://left",
        digest="1" * 64,
        category="source",
    )
    right = EvidenceRef(
        source="knowledge://right",
        digest="2" * 64,
        category="source",
    )

    first = _knowledge(refs=(left, right, left))
    second = _knowledge(refs=(right, left))

    assert first.provenance_refs == second.provenance_refs
    left_decision = _evaluate(knowledge=(first,))
    right_decision = _evaluate(knowledge=(second,))
    assert left_decision.knowledge_digest == right_decision.knowledge_digest
    assert left_decision.decision_digest == right_decision.decision_digest


def test_independent_quality_rejection_and_floor_fail_closed() -> None:
    rejected = _evaluate(quality_report=_quality(accepted=False, score=0.95))
    assert rejected.accepted is False
    assert "independent-quality-rejected" in rejected.reasons

    low = _evaluate(quality_report=_quality(accepted=True, score=0.60))
    assert low.accepted is False
    assert "independent-quality-below-floor" in low.reasons


def test_policy_can_explicitly_allow_review_and_partial_retrieval() -> None:
    policy = IntelligenceQualityPolicy(
        allow_memory_review=True,
        allow_partial_retrieval=True,
    )
    decision = _evaluate(
        memory_decisions=(_memory(action=MemoryAction.REVIEW),),
        retrieval_receipt=_retrieval(partial=True),
        policy=policy,
    )

    assert decision.accepted is True


def test_rejected_decision_cannot_become_promotion_evidence() -> None:
    decision = _evaluate(quality_report=_quality(accepted=False))

    assert decision.accepted is False
    with pytest.raises(IntelligenceQualityError, match="cannot become"):
        decision.accepted_evidence_ref()


@pytest.mark.parametrize("score", (-0.01, 1.01, float("inf"), float("nan")))
def test_malformed_memory_score_fails_closed(score: float) -> None:
    with pytest.raises(IntelligenceQualityError, match="memory score"):
        _evaluate(memory_decisions=(_memory(score=score),))


@pytest.mark.parametrize("score", (-0.01, 1.01, float("inf"), float("nan")))
def test_malformed_independent_quality_score_fails_closed(score: float) -> None:
    with pytest.raises(IntelligenceQualityError, match="quality_report.score"):
        _evaluate(quality_report=_quality(score=score))


def test_resolved_conflict_is_bound_but_does_not_block() -> None:
    conflict = replace(
        _unresolved_conflict(),
        resolution=MemoryConflictResolution.KEEP_BOTH,
        reason="independent provenance supports both scoped claims",
    )

    decision = _evaluate(memory_conflicts=(conflict,))

    assert decision.accepted is True
    assert decision.reasons == ()
    assert len(decision.conflict_digest) == 64
