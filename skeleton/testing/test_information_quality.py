from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.intelligence.information_quality import (
    InformationQualityError,
    InformationQualityPolicy,
    build_information_quality_receipt,
    observe_knowledge_document,
)
from skeleton.intelligence.knowledge_base import Document
from skeleton.memory.reconciliation import (
    MemoryAction,
    MemoryConflictCandidate,
    MemoryConflictResolver,
    MemoryDecision,
)
from skeleton.retrieval.freshness import PlaneFreshness
from skeleton.retrieval.receipts import RetrievalReceipt


NOW = 200.0
NOW_NS = 200_000_000_000


def _memory(
    record_id: str = "memory-a",
    *,
    action: MemoryAction = MemoryAction.RETAIN,
) -> MemoryDecision:
    return MemoryDecision(
        record_id=record_id,
        action=action,
        score=0.91,
        reasons=(),
        signals=(
            ("freshness", 0.9),
            ("utility", 0.8),
            ("evidence", 0.9),
            ("contradiction", 0.0),
        ),
    )


def _candidate(
    record_id: str,
    digest_char: str,
    *,
    confidence: float,
) -> MemoryConflictCandidate:
    return MemoryConflictCandidate(
        record_id=record_id,
        scope_key="tenant-a:user-a:project-a",
        claim_key="preferred-language",
        payload_digest=digest_char * 64,
        confidence=confidence,
        provenance_count=3,
        updated_at=100.0,
    )


def _unresolved_conflict():
    return MemoryConflictResolver().build(
        (
            _candidate("a", "a", confidence=0.80),
            _candidate("b", "b", confidence=0.75),
        ),
        created_at=100.0,
    )


def _retrieval(
    *,
    scope_digest: str = "scope-abc",
    partial: bool = False,
    failed_planes: tuple[str, ...] = (),
) -> RetrievalReceipt:
    return RetrievalReceipt(
        receipt_id="retrieval-1",
        query_digest="query-digest",
        generation=7,
        scope_digest=scope_digest,
        considered_planes=("rag", "kag"),
        candidate_planes=("rag", "kag"),
        failed_planes=failed_planes,
        fragment_planes=(
            ("rag-1", ("rag",)),
            ("kag-1", ("kag",)),
        ),
        partial=partial,
        created_ns=123,
        source="live",
    )


def _freshness(
    *,
    rag_indexed_at: float = 190.0,
    kag_indexed_at: float = 190.0,
    stale_after_s: float = 30.0,
):
    return {
        "rag": PlaneFreshness(
            plane="rag",
            index_version="rag-index-7",
            source_revision="rag-source-7",
            indexed_at=rag_indexed_at,
            stale_after_s=stale_after_s,
        ),
        "kag": PlaneFreshness(
            plane="kag",
            index_version="kag-index-4",
            source_revision="kag-source-4",
            indexed_at=kag_indexed_at,
            stale_after_s=stale_after_s,
        ),
    }


def _document(
    *,
    doc_id: str = "runbook",
    body: str = "restart the service",
    updated_ns: int = 190_000_000_000,
) -> Document:
    return Document(
        doc_id=doc_id,
        title="Service runbook",
        body=body,
        tags=["ops"],
        subsystems=["api"],
        version=3,
        updated_ns=updated_ns,
    )


def _knowledge(
    *,
    doc_id: str = "runbook",
    updated_ns: int = 190_000_000_000,
    stale_after_ns: int = 30_000_000_000,
    contradiction_count: int = 0,
    contradiction_resolution_refs: tuple[str, ...] = (),
):
    return observe_knowledge_document(
        _document(doc_id=doc_id, updated_ns=updated_ns),
        source_revision="git:abc123",
        provenance_refs=("source:runbooks/api.md",),
        stale_after_ns=stale_after_ns,
        contradiction_count=contradiction_count,
        contradiction_resolution_refs=contradiction_resolution_refs,
    )


def _receipt(**overrides):
    args = {
        "memory_decisions": (_memory(),),
        "memory_conflicts": (),
        "retrieval_receipt": _retrieval(),
        "retrieval_freshness": _freshness(),
        "knowledge_observations": (_knowledge(),),
        "now": NOW,
        "now_ns": NOW_NS,
        "policy": InformationQualityPolicy(),
    }
    args.update(overrides)
    return build_information_quality_receipt(**args)


def test_joined_information_quality_receipt_is_promotion_eligible() -> None:
    receipt = _receipt()

    assert receipt.eligible_for_promotion is True
    assert receipt.blockers == ()
    assert receipt.memory_record_ids == ("memory-a",)
    assert receipt.retrieval_receipt_id == "retrieval-1"
    assert receipt.retrieval_scope_digest == "scope-abc"
    assert receipt.stale_retrieval_planes == ()
    assert receipt.missing_retrieval_freshness == ()
    assert receipt.knowledge_document_ids == ("runbook",)
    assert receipt.stale_knowledge_document_ids == ()
    assert receipt.unresolved_knowledge_document_ids == ()
    assert len(receipt.receipt_digest) == 64
    evidence = receipt.evidence_ref()
    assert evidence.digest == receipt.receipt_digest
    assert evidence.category == "information_quality"


@pytest.mark.parametrize(
    ("action", "blocker"),
    (
        (MemoryAction.REVIEW, "memory_not_retained"),
        (MemoryAction.TOMBSTONE, "memory_not_retained"),
    ),
)
def test_non_retained_memory_blocks_promotion(
    action: MemoryAction,
    blocker: str,
) -> None:
    receipt = _receipt(memory_decisions=(_memory(action=action),))

    assert blocker in receipt.blockers
    assert receipt.eligible_for_promotion is False
    with pytest.raises(InformationQualityError, match="cannot become"):
        receipt.evidence_ref()


def test_unresolved_memory_conflict_blocks_promotion() -> None:
    conflict = _unresolved_conflict()
    receipt = _receipt(memory_conflicts=(conflict,))

    assert receipt.unresolved_memory_conflict_ids == (conflict.conflict_id,)
    assert "unresolved_memory_conflict" in receipt.blockers


@pytest.mark.parametrize(
    ("retrieval", "blocker"),
    (
        (_retrieval(scope_digest=""), "retrieval_scope_missing"),
        (_retrieval(partial=True), "retrieval_partial"),
        (_retrieval(failed_planes=("rag",)), "retrieval_plane_failed"),
    ),
)
def test_retrieval_contract_failures_block_promotion(
    retrieval: RetrievalReceipt,
    blocker: str,
) -> None:
    receipt = _receipt(retrieval_receipt=retrieval)

    assert blocker in receipt.blockers
    assert receipt.eligible_for_promotion is False


def test_missing_or_stale_retrieval_freshness_blocks_promotion() -> None:
    missing = _freshness()
    del missing["kag"]
    missing_receipt = _receipt(retrieval_freshness=missing)

    assert missing_receipt.missing_retrieval_freshness == ("kag",)
    assert "retrieval_freshness_missing" in missing_receipt.blockers

    stale = _freshness(rag_indexed_at=100.0)
    stale_receipt = _receipt(retrieval_freshness=stale)

    assert stale_receipt.stale_retrieval_planes == ("rag",)
    assert "retrieval_plane_stale" in stale_receipt.blockers


def test_stale_knowledge_blocks_promotion() -> None:
    stale = _knowledge(
        updated_ns=100_000_000_000,
        stale_after_ns=50_000_000_000,
    )
    receipt = _receipt(knowledge_observations=(stale,))

    assert receipt.stale_knowledge_document_ids == ("runbook",)
    assert "knowledge_stale" in receipt.blockers


def test_unresolved_knowledge_contradiction_blocks_until_resolution_bound() -> None:
    unresolved = _knowledge(contradiction_count=2)
    blocked = _receipt(knowledge_observations=(unresolved,))

    assert blocked.unresolved_knowledge_document_ids == ("runbook",)
    assert "knowledge_contradiction_unresolved" in blocked.blockers

    resolved = _knowledge(
        contradiction_count=2,
        contradiction_resolution_refs=("verification:conflict-resolution-7",),
    )
    accepted = _receipt(knowledge_observations=(resolved,))

    assert accepted.unresolved_knowledge_document_ids == ()
    assert "knowledge_contradiction_unresolved" not in accepted.blockers
    assert accepted.eligible_for_promotion is True


def test_knowledge_observation_requires_lineage() -> None:
    with pytest.raises(InformationQualityError, match="provenance_refs"):
        observe_knowledge_document(
            _document(),
            source_revision="git:abc123",
            provenance_refs=(),
            stale_after_ns=30_000_000_000,
        )


def test_document_content_is_digest_bound_not_embedded_in_receipt() -> None:
    observation = _knowledge()
    receipt = _receipt(knowledge_observations=(observation,))
    rendered = repr(receipt.payload())

    assert "restart the service" not in rendered
    assert observation.content_digest in receipt.knowledge_digest or (
        len(receipt.knowledge_digest) == 64
    )


def test_input_order_is_canonical() -> None:
    first_memory = _memory("a")
    second_memory = _memory("z")
    first_knowledge = _knowledge(doc_id="a-doc")
    second_knowledge = _knowledge(doc_id="z-doc")

    left = _receipt(
        memory_decisions=(second_memory, first_memory),
        knowledge_observations=(second_knowledge, first_knowledge),
    )
    right = _receipt(
        memory_decisions=(first_memory, second_memory),
        knowledge_observations=(first_knowledge, second_knowledge),
    )

    assert left.receipt_digest == right.receipt_digest
    assert left.identity_payload() == right.identity_payload()


def test_time_progression_changes_identity_only_when_freshness_class_changes() -> None:
    early = _receipt(now=200.0, now_ns=200_000_000_000)
    same_class = _receipt(now=205.0, now_ns=205_000_000_000)

    assert early.receipt_digest == same_class.receipt_digest

    late = _receipt(now=221.0, now_ns=221_000_000_000)
    assert late.receipt_digest != early.receipt_digest
    assert "retrieval_plane_stale" in late.blockers
    assert "knowledge_stale" in late.blockers


def test_policy_can_only_relax_explicitly_and_changes_identity() -> None:
    blocked = _receipt(
        retrieval_receipt=_retrieval(partial=True),
    )
    relaxed_policy = InformationQualityPolicy(
        allow_partial_retrieval=True,
    )
    relaxed = _receipt(
        retrieval_receipt=_retrieval(partial=True),
        policy=relaxed_policy,
    )

    assert blocked.eligible_for_promotion is False
    assert relaxed.eligible_for_promotion is True
    assert blocked.policy_digest != relaxed.policy_digest
    assert blocked.receipt_digest != relaxed.receipt_digest
