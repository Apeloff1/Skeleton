from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.observability.operations_review import (
    OperationsEvidence,
    OperationsReviewError,
    build_operations_review,
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def evidence() -> dict[str, str]:
    return {
        "slo_assessment_digest": sha("slo"),
        "budget_decision_digest": sha("budget"),
        "cardinality_decision_digest": sha("cardinality"),
        "trace_evidence_digest": sha("trace"),
        "profile_finding_digest": sha("profile"),
        "latency_assessment_digest": sha("latency"),
        "cost_decision_digest": sha("cost"),
        "efficiency_claim_digest": sha("efficiency"),
    }


def healthy() -> dict[str, bool]:
    return {
        "slo_target_met": True,
        "budget_healthy": True,
        "cardinality_accepted": True,
        "profile_not_regressed": True,
        "latency_within_budget": True,
        "cost_admitted": True,
        "efficiency_claim_valid": True,
    }


def test_operations_review_binds_all_eight_volume_evidence_surfaces() -> None:
    review=build_operations_review(
        review_id="review-1",
        subject_id="assistant-prod",
        source_revision="a"*40,
        evidence_digests=evidence(),
        status_inputs=healthy(),
    )
    assert review.status=="healthy"
    assert review.blockers==()
    assert review.promotion_authority is False
    assert len(review.digest)==64


def test_failed_operational_signals_are_never_hidden() -> None:
    statuses=healthy()
    statuses["latency_within_budget"]=False
    statuses["cost_admitted"]=False
    review=build_operations_review(
        review_id="review-2",
        subject_id="assistant-prod",
        source_revision="b"*40,
        evidence_digests=evidence(),
        status_inputs=statuses,
    )
    assert review.status=="attention_required"
    assert review.blockers==("cost_admitted","latency_within_budget")


def test_missing_evidence_surface_fails_closed() -> None:
    payload=evidence()
    payload.pop("trace_evidence_digest")
    with pytest.raises(OperationsReviewError,match="exact operations evidence set"):
        build_operations_review(
            review_id="review",
            subject_id="subject",
            source_revision="c"*40,
            evidence_digests=payload,
            status_inputs=healthy(),
        )


def test_forged_healthy_status_is_rejected() -> None:
    statuses=healthy()
    statuses["budget_healthy"]=False
    with pytest.raises(OperationsReviewError,match="status must match blocker evidence"):
        OperationsEvidence(
            review_id="forged",
            subject_id="subject",
            source_revision="d"*40,
            status_inputs=statuses,
            blockers=("budget_healthy",),
            status="healthy",
            promotion_authority=False,
            **evidence(),
        )


def test_operations_review_cannot_claim_promotion_authority() -> None:
    with pytest.raises(OperationsReviewError,match="cannot grant promotion authority"):
        OperationsEvidence(
            review_id="unsafe",
            subject_id="subject",
            source_revision="e"*40,
            status_inputs=healthy(),
            blockers=(),
            status="healthy",
            promotion_authority=True,
            **evidence(),
        )
