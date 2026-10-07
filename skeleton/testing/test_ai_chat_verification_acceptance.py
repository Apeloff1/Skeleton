from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from skeleton.ai.assistant.verification_acceptance import (
    CHAT_VERIFICATION_PROFILES,
    ChatVerificationAcceptanceError,
    ChatVerificationDisposition,
    ChatVerificationProfile,
    evaluate_chat_verification,
)
from skeleton.contracts.verification import (
    VerificationLevel,
    VerificationOutcome,
    VerificationReceipt,
)


NOW = datetime(2026, 10, 7, 3, 30, tzinfo=UTC)
OPERATION_ID = "11111111-1111-4111-8111-111111111111"
OTHER_OPERATION_ID = "22222222-2222-4222-8222-222222222222"
EXECUTION_ID = "execution-1"
CLAIM_ID = "33333333-3333-4333-8333-333333333333"
OTHER_CLAIM_ID = "44444444-4444-4444-8444-444444444444"
EVIDENCE_ID = "55555555-5555-4555-8555-555555555555"
POSTCONDITION_ID = "66666666-6666-4666-8666-666666666666"
CHECK_ID = "99999999-9999-4999-8999-999999999999"


def verification_receipt(
    *,
    receipt_id: str = "77777777-7777-4777-8777-777777777777",
    claim_id: str = CLAIM_ID,
    operation_id: str = OPERATION_ID,
    execution_id: str = EXECUTION_ID,
    outcome: VerificationOutcome = VerificationOutcome.PASSED,
    level: VerificationLevel = VerificationLevel.STRUCTURAL,
    modes: tuple[str, ...] = ("structural",),
    policy_satisfied: bool = True,
    supporting: tuple[str, ...] = (),
    independent: bool = False,
    postconditions: tuple[str, ...] = (),
    verified_at: datetime = NOW - timedelta(seconds=10),
) -> VerificationReceipt:
    return VerificationReceipt(
        receipt_id=receipt_id,
        claim_id=claim_id,
        claim_digest="a" * 64,
        tenant_id="tenant-a",
        outcome=outcome,
        policy_level=level,
        required_modes=modes,
        policy_satisfied=policy_satisfied,
        verifier_id="canonical-verifier",
        verified_at=verified_at,
        check_id=CHECK_ID if policy_satisfied else None,
        operation_id=operation_id,
        execution_id=execution_id,
        supporting_evidence_ids=supporting,
        postcondition_observation_ids=postconditions,
        independent=independent,
    )


def evaluate(profile: ChatVerificationProfile, *receipts: VerificationReceipt):
    return evaluate_chat_verification(
        profile=profile,
        receipts=receipts,
        operation_id=OPERATION_ID,
        execution_id=EXECUTION_ID,
        finalized_at=NOW,
    )


def test_structural_profile_accepts_canonical_passed_receipt() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["structural"],
        verification_receipt(),
    )
    assert decision.accepted is True
    assert decision.quarantined is False
    assert decision.disposition is ChatVerificationDisposition.ACCEPT
    assert decision.reasons == ()
    assert decision.production_authority is False
    assert decision.reference == (
        "chat-verification-acceptance-sha256:" + decision.digest
    )


def test_grounded_profile_requires_evidence_level_and_support() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["grounded"],
        verification_receipt(),
    )
    assert decision.accepted is False
    assert "verification_level_below_profile" in decision.reasons
    assert "verification_required_mode_missing" in decision.reasons
    assert "verification_supporting_evidence_missing" in decision.reasons


def test_grounded_profile_accepts_fresh_supported_evidence_receipt() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["grounded"],
        verification_receipt(
            level=VerificationLevel.EVIDENCE,
            modes=("structural", "evidence"),
            supporting=(EVIDENCE_ID,),
        ),
    )
    assert decision.accepted is True


def test_grounded_profile_rejects_stale_receipt() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["grounded"],
        verification_receipt(
            level=VerificationLevel.EVIDENCE,
            modes=("structural", "evidence"),
            supporting=(EVIDENCE_ID,),
            verified_at=NOW - timedelta(hours=2),
        ),
    )
    assert decision.accepted is False
    assert "verification_receipt_stale" in decision.reasons


def test_future_verification_receipt_fails_closed() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["structural"],
        verification_receipt(
            verified_at=NOW + timedelta(seconds=1),
        ),
    )
    assert decision.accepted is False
    assert "verification_receipt_from_future" in decision.reasons


def test_high_assurance_requires_independent_receipt() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["high_assurance"],
        verification_receipt(
            level=VerificationLevel.EVIDENCE,
            modes=("structural", "evidence", "independent"),
            supporting=(EVIDENCE_ID,),
            independent=False,
        ),
    )
    assert decision.accepted is False
    assert "independent_verification_receipt_missing" in decision.reasons


def test_high_assurance_accepts_independent_canonical_receipt() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["high_assurance"],
        verification_receipt(
            level=VerificationLevel.INDEPENDENT,
            modes=("structural", "evidence", "independent"),
            supporting=(EVIDENCE_ID,),
            independent=True,
        ),
    )
    assert decision.accepted is True
    assert decision.independent_receipt_count == 1


def test_contested_receipt_quarantines_instead_of_publishing() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["grounded"],
        verification_receipt(
            outcome=VerificationOutcome.CONTESTED,
            level=VerificationLevel.EVIDENCE,
            policy_satisfied=False,
            modes=("structural", "evidence"),
            supporting=(EVIDENCE_ID,),
        ),
    )
    assert decision.accepted is False
    assert decision.quarantined is True
    assert decision.disposition is ChatVerificationDisposition.QUARANTINE
    assert "verification_outcome_requires_quarantine" in decision.reasons


def test_policy_unsatisfied_receipt_is_rejected() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["structural"],
        verification_receipt(policy_satisfied=False),
    )
    assert decision.accepted is False
    assert "verification_policy_not_satisfied" in decision.reasons


def test_postcondition_profile_requires_observation() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["action_postcondition"],
        verification_receipt(
            level=VerificationLevel.INDEPENDENT,
            modes=(
                "structural",
                "evidence",
                "independent",
                "postcondition",
            ),
            supporting=(EVIDENCE_ID,),
            independent=True,
        ),
    )
    assert decision.accepted is False
    assert "postcondition_observation_missing" in decision.reasons


def test_postcondition_profile_accepts_observed_action_outcome() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["action_postcondition"],
        verification_receipt(
            level=VerificationLevel.POSTCONDITION,
            modes=(
                "structural",
                "evidence",
                "independent",
                "postcondition",
            ),
            supporting=(EVIDENCE_ID,),
            independent=True,
            postconditions=(POSTCONDITION_ID,),
        ),
    )
    assert decision.accepted is True
    assert decision.postcondition_observation_count == 1


def test_operation_identity_drift_is_rejected() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["structural"],
        verification_receipt(operation_id=OTHER_OPERATION_ID),
    )
    assert decision.accepted is False
    assert "verification_operation_identity_mismatch" in decision.reasons


def test_execution_identity_drift_is_rejected() -> None:
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["structural"],
        verification_receipt(execution_id="execution-2"),
    )
    assert decision.accepted is False
    assert "verification_execution_identity_mismatch" in decision.reasons


def test_duplicate_claim_verification_is_rejected() -> None:
    first = verification_receipt()
    second = verification_receipt(
        receipt_id="88888888-8888-4888-8888-888888888888",
    )
    decision = evaluate(
        CHAT_VERIFICATION_PROFILES["structural"],
        first,
        second,
    )
    assert decision.accepted is False
    assert "duplicate_claim_verification" in decision.reasons


def test_empty_receipt_set_fails_closed() -> None:
    with pytest.raises(
        ChatVerificationAcceptanceError,
        match="must not be empty",
    ):
        evaluate_chat_verification(
            profile=CHAT_VERIFICATION_PROFILES["structural"],
            receipts=(),
            operation_id=OPERATION_ID,
            execution_id=EXECUTION_ID,
            finalized_at=NOW,
        )


def test_profile_rejects_allowed_quarantine_overlap() -> None:
    with pytest.raises(
        ChatVerificationAcceptanceError,
        match="must not overlap",
    ):
        ChatVerificationProfile(
            profile_id="bad-profile",
            allowed_outcomes=(
                VerificationOutcome.PASSED,
                VerificationOutcome.CONTESTED,
            ),
            quarantine_outcomes=(VerificationOutcome.CONTESTED,),
        )


def test_decision_is_content_minimized_and_deterministic() -> None:
    receipt = verification_receipt(
        level=VerificationLevel.EVIDENCE,
        modes=("structural", "evidence"),
        supporting=(EVIDENCE_ID,),
    )
    first = evaluate(CHAT_VERIFICATION_PROFILES["grounded"], receipt)
    second = evaluate(CHAT_VERIFICATION_PROFILES["grounded"], receipt)
    assert first.digest == second.digest
    encoded = str(first.as_dict())
    assert EVIDENCE_ID not in encoded
    assert "canonical-verifier" not in encoded
    assert "tenant-a" not in encoded
