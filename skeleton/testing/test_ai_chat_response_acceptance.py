from __future__ import annotations

from datetime import UTC, datetime, timedelta

from skeleton.ai.assistant.evidence import (
    ClaimEvidenceReceipt,
    PublicationDisposition,
)
from skeleton.ai.assistant.response_acceptance import (
    LiveResponseAcceptancePolicy,
    ResponseAcceptancePolicy,
    evaluate_live_response_acceptance,
    evaluate_response_acceptance,
)
from skeleton.contracts.verification import (
    ClaimKind,
    VerificationClaim,
    VerificationRisk,
)


NOW = datetime(2026, 10, 6, 13, 0, tzinfo=UTC)
CLAIM_ID = "11111111-1111-4111-8111-111111111111"
OTHER_CLAIM_ID = "22222222-2222-4222-8222-222222222222"


def claim(
    *,
    claim_id: str = CLAIM_ID,
    kind: ClaimKind = ClaimKind.FACT,
    risk: VerificationRisk = VerificationRisk.LOW,
    text: str = "System A decreases latency by 10 percent.",
) -> VerificationClaim:
    return VerificationClaim(
        claim_id=claim_id,
        tenant_id="tenant-a",
        text=text,
        kind=kind,
        risk=risk,
        created_at=NOW - timedelta(minutes=1),
        generated_by_model=True,
    )


def receipt(
    claim_value: VerificationClaim,
    *,
    disposition: PublicationDisposition = PublicationDisposition.PUBLISH,
    evaluated_at: datetime = NOW - timedelta(seconds=10),
    claim_digest: str | None = None,
) -> ClaimEvidenceReceipt:
    supporting = (
        ("evidence-a",)
        if disposition
        in {
            PublicationDisposition.PUBLISH,
            PublicationDisposition.PUBLISH_WITH_QUALIFICATION,
        }
        else ()
    )
    contradicting = (
        ("evidence-b",)
        if disposition is PublicationDisposition.CONTESTED
        else ()
    )
    reasons = (
        ("independent_origin_requirement_not_met",)
        if disposition is PublicationDisposition.PUBLISH_WITH_QUALIFICATION
        else ()
    )
    return ClaimEvidenceReceipt(
        claim_id=claim_value.claim_id,
        claim_digest=claim_digest or claim_value.digest,
        claim_identity_sha256="a" * 64,
        policy_digest="b" * 64,
        disposition=disposition,
        reasons=reasons,
        supporting_evidence_ids=supporting,
        contradicting_evidence_ids=contradicting,
        context_evidence_ids=(),
        rejected_evidence_ids=(),
        supporting_origin_ids=("origin-a",) if supporting else (),
        assessments=(),
        evaluated_at=evaluated_at,
    )


def policy(**kwargs) -> ResponseAcceptancePolicy:
    values = {
        "policy_id": "chat-response-acceptance-v1",
        "required_claim_kinds": (
            ClaimKind.FACT,
            ClaimKind.ACTION_OUTCOME,
        ),
        "allow_qualified_low_risk": True,
        "max_receipt_age_s": None,
    }
    values.update(kwargs)
    return ResponseAcceptancePolicy(**values)


def evaluate(claims, receipts, *, policy_value=None):
    return evaluate_response_acceptance(
        claims=claims,
        receipts=receipts,
        policy=policy_value or policy(),
        finalized_at=NOW,
    )


def test_publishable_fact_is_accepted() -> None:
    item = claim()
    decision = evaluate([item], [receipt(item)])
    assert decision.accepted is True
    assert decision.accepted_claim_ids == (CLAIM_ID,)
    assert decision.missing_receipt_claim_ids == ()


def test_required_fact_without_receipt_fails_closed() -> None:
    item = claim()
    decision = evaluate([item], [])
    assert decision.accepted is False
    assert decision.missing_receipt_claim_ids == (CLAIM_ID,)


def test_interpretation_does_not_require_evidence_by_default() -> None:
    item = claim(kind=ClaimKind.INTERPRETATION)
    decision = evaluate([item], [])
    assert decision.accepted is True
    assert decision.required_claim_ids == ()


def test_action_outcome_requires_receipt_by_default() -> None:
    item = claim(kind=ClaimKind.ACTION_OUTCOME)
    decision = evaluate([item], [])
    assert decision.accepted is False
    assert decision.required_claim_ids == (CLAIM_ID,)


def test_contested_required_claim_blocks_acceptance() -> None:
    item = claim()
    decision = evaluate(
        [item],
        [receipt(item, disposition=PublicationDisposition.CONTESTED)],
    )
    assert decision.accepted is False
    assert decision.rejected_claim_ids == (CLAIM_ID,)
    assert "required_claim_contested" in decision.reasons


def test_abstained_required_claim_blocks_acceptance() -> None:
    item = claim()
    decision = evaluate(
        [item],
        [receipt(item, disposition=PublicationDisposition.ABSTAIN)],
    )
    assert decision.accepted is False
    assert "required_claim_abstained" in decision.reasons


def test_low_risk_qualified_claim_can_be_accepted() -> None:
    item = claim(risk=VerificationRisk.LOW)
    decision = evaluate(
        [item],
        [
            receipt(
                item,
                disposition=PublicationDisposition.PUBLISH_WITH_QUALIFICATION,
            )
        ],
    )
    assert decision.accepted is True
    assert decision.qualified_claim_ids == (CLAIM_ID,)


def test_high_risk_qualified_claim_is_not_accepted() -> None:
    item = claim(risk=VerificationRisk.HIGH)
    decision = evaluate(
        [item],
        [
            receipt(
                item,
                disposition=PublicationDisposition.PUBLISH_WITH_QUALIFICATION,
            )
        ],
    )
    assert decision.accepted is False
    assert "required_claim_qualification_not_admitted" in decision.reasons


def test_policy_can_disallow_low_risk_qualification() -> None:
    item = claim()
    decision = evaluate(
        [item],
        [
            receipt(
                item,
                disposition=PublicationDisposition.PUBLISH_WITH_QUALIFICATION,
            )
        ],
        policy_value=policy(allow_qualified_low_risk=False),
    )
    assert decision.accepted is False


def test_claim_receipt_digest_mismatch_blocks_acceptance() -> None:
    item = claim()
    decision = evaluate(
        [item],
        [receipt(item, claim_digest="c" * 64)],
    )
    assert decision.accepted is False
    assert "claim_receipt_digest_mismatch" in decision.reasons


def test_future_receipt_blocks_acceptance() -> None:
    item = claim()
    decision = evaluate(
        [item],
        [receipt(item, evaluated_at=NOW + timedelta(seconds=1))],
    )
    assert decision.accepted is False
    assert "claim_receipt_from_future" in decision.reasons


def test_stale_receipt_blocks_acceptance_when_policy_binds_age() -> None:
    item = claim()
    decision = evaluate(
        [item],
        [receipt(item, evaluated_at=NOW - timedelta(hours=2))],
        policy_value=policy(max_receipt_age_s=3600),
    )
    assert decision.accepted is False
    assert "claim_receipt_stale" in decision.reasons


def test_duplicate_claim_identity_blocks_acceptance() -> None:
    item = claim()
    decision = evaluate(
        [item, item],
        [receipt(item)],
    )
    assert decision.accepted is False
    assert "duplicate_claim_id" in decision.reasons


def test_duplicate_receipt_for_claim_blocks_acceptance() -> None:
    item = claim()
    value = receipt(item)
    decision = evaluate([item], [value, value])
    assert decision.accepted is False
    assert "duplicate_receipt_for_claim" in decision.reasons


def test_receipt_for_unknown_claim_blocks_acceptance() -> None:
    item = claim()
    other = claim(
        claim_id=OTHER_CLAIM_ID,
        text="System B increases throughput by 5 percent.",
    )
    decision = evaluate(
        [item],
        [receipt(item), receipt(other)],
    )
    assert decision.accepted is False
    assert "receipt_for_unknown_claim" in decision.reasons


def test_multiple_required_claims_all_need_accepted_receipts() -> None:
    first = claim()
    second = claim(
        claim_id=OTHER_CLAIM_ID,
        text="System B increases throughput by 5 percent.",
    )
    decision = evaluate(
        [first, second],
        [receipt(first)],
    )
    assert decision.accepted is False
    assert decision.missing_receipt_claim_ids == (OTHER_CLAIM_ID,)


def test_acceptance_decision_is_deterministic_and_non_executing() -> None:
    item = claim()
    first = evaluate([item], [receipt(item)])
    second = evaluate([item], [receipt(item)])
    assert first.digest == second.digest
    assert first.authority_scope == "response-acceptance-decision-only"
    assert first.production_authority is False



def live_acceptance(**overrides):
    values = {
        "operation_id": "operation-1",
        "observed_operation_id": "operation-1",
        "expected_execution_id": "execution-1",
        "observed_execution_id": "execution-1",
        "context_digest": "d" * 64,
        "final_output": "Verified answer.",
        "verification": "verification:engine-v1",
        "provider_receipts": ("provider:local:receipt-1",),
        "tool_receipts": (),
        "evidence_refs": ("evidence:answer-1",),
    }
    values.update(overrides)
    return evaluate_live_response_acceptance(**values)


def test_live_engine_response_is_bound_before_commit() -> None:
    receipt_value = live_acceptance()
    assert receipt_value.accepted is True
    assert receipt_value.reasons == ()
    assert receipt_value.expected_execution_id == "execution-1"
    assert receipt_value.observed_execution_id == "execution-1"
    assert receipt_value.context_digest == "d" * 64
    assert len(receipt_value.output_sha256 or "") == 64
    assert receipt_value.artifact_ref == (
        "response-acceptance-sha256:" + receipt_value.digest
    )


def test_live_response_acceptance_rejects_operation_identity_drift() -> None:
    receipt_value = live_acceptance(observed_operation_id="operation-2")
    assert receipt_value.accepted is False
    assert "operation_identity_mismatch" in receipt_value.reasons


def test_live_response_acceptance_rejects_execution_identity_drift() -> None:
    receipt_value = live_acceptance(observed_execution_id="execution-2")
    assert receipt_value.accepted is False
    assert "execution_identity_mismatch" in receipt_value.reasons


def test_live_response_acceptance_requires_provider_receipt() -> None:
    receipt_value = live_acceptance(provider_receipts=())
    assert receipt_value.accepted is False
    assert "provider_receipt_missing" in receipt_value.reasons


def test_live_response_acceptance_rejects_unverified_output() -> None:
    receipt_value = live_acceptance(verification="unverified")
    assert receipt_value.accepted is False
    assert "verification_not_accepted" in receipt_value.reasons


def test_live_response_acceptance_rejects_malformed_provider_receipt() -> None:
    receipt_value = live_acceptance(
        provider_receipts=("receipt-without-provider-prefix",)
    )
    assert receipt_value.accepted is False
    assert "provider_receipt_prefix_invalid" in receipt_value.reasons
    assert "provider_receipt_missing" in receipt_value.reasons


def test_live_response_acceptance_rejects_duplicate_receipt_identity() -> None:
    receipt_value = live_acceptance(
        provider_receipts=(
            "provider:local:receipt-1",
            "provider:local:receipt-1",
        )
    )
    assert receipt_value.accepted is False
    assert "provider_receipt_duplicate" in receipt_value.reasons


def test_live_response_acceptance_enforces_output_hard_bound() -> None:
    receipt_value = live_acceptance(
        final_output="abcdefghij",
        policy=LiveResponseAcceptancePolicy(max_output_utf8_bytes=8),
    )
    assert receipt_value.accepted is False
    assert "output_size_exceeded" in receipt_value.reasons
    assert receipt_value.output_sha256 is None


def test_live_response_receipt_is_content_minimized_and_deterministic() -> None:
    first = live_acceptance()
    second = live_acceptance()
    assert first.digest == second.digest
    encoded = str(first.as_dict())
    assert "Verified answer." not in encoded
    assert "provider:local:receipt-1" not in encoded
    assert "evidence:answer-1" not in encoded
    assert first.production_authority is False
    assert first.authority_scope == "live-response-acceptance-decision-only"



def test_live_response_receipt_is_order_invariant_for_receipt_sets() -> None:
    first = live_acceptance(
        provider_receipts=(
            "provider:local:receipt-a",
            "provider:local:receipt-b",
        ),
        evidence_refs=("evidence:a", "evidence:b"),
    )
    second = live_acceptance(
        provider_receipts=(
            "provider:local:receipt-b",
            "provider:local:receipt-a",
        ),
        evidence_refs=("evidence:b", "evidence:a"),
    )
    assert first.accepted is True
    assert second.accepted is True
    assert first.digest == second.digest
