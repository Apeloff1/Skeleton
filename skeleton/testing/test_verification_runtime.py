from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.verification import (
    Claim,
    ClaimKind,
    ConfidenceBand,
    EvidenceReference,
    PostconditionCheck,
    RiskClass,
    VerificationLevel,
    VerificationOutcome,
    VerificationRequest,
    content_digest,
)
from skeleton.intelligence.verification_policy import VerificationPolicy
from skeleton.intelligence.verification_runtime import (
    CanonicalProviderSemanticVerifier,
    DeterministicVerificationInput,
    SemanticVerificationDecision,
    VerificationRuntime,
    tool_receipt_postcondition,
    verify_with_semantic,
)
from skeleton.skills.tool_contract import (
    ToolExecutionReceipt,
    ToolExecutionStatus,
)


def _now() -> datetime:
    return datetime(2026, 9, 23, 18, 30, tzinfo=timezone.utc)


def _evidence(
    evidence_id: str = "ev-1",
    *,
    content: str = "supported fact",
    citation_id: str = "cite-1",
) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        source_type="retrieval",
        source_id="source-1",
        content_digest=content_digest(content),
        provenance={"source": "test"},
        observed_at=_now(),
        authority_class="primary",
        citation_metadata={"citation_id": citation_id},
        tenant_id="tenant-a",
    )


def _request(
    level: VerificationLevel,
    *,
    evidence_refs=("ev-1",),
    tool_receipt_refs=(),
    deadline=None,
) -> VerificationRequest:
    return VerificationRequest(
        verification_id="ver-1",
        operation_id="op-1",
        execution_id="exec-1",
        turn_id="turn-1",
        capability="assistant.answer",
        risk_class=RiskClass.MEDIUM,
        required_level=level,
        candidate_ref="candidate:1",
        context_snapshot_id="context:1",
        evidence_refs=tuple(evidence_refs),
        tool_receipt_refs=tuple(tool_receipt_refs),
        budget={"max_repairs": 1},
        deadline=deadline,
    )


def test_policy_maps_risk_and_escalates_for_effects() -> None:
    policy = VerificationPolicy()

    assert policy.select_level(
        risk_class=RiskClass.LOW,
        capability="assistant.answer",
    ) is VerificationLevel.STRUCTURAL
    assert policy.select_level(
        risk_class=RiskClass.MEDIUM,
        capability="assistant.answer",
    ) is VerificationLevel.EVIDENCE
    assert policy.select_level(
        risk_class=RiskClass.HIGH,
        capability="assistant.answer",
    ) is VerificationLevel.ACTION
    assert policy.select_level(
        risk_class=RiskClass.CRITICAL,
        capability="assistant.answer",
    ) is VerificationLevel.HIGH_IMPACT

    assert policy.select_level(
        risk_class=RiskClass.LOW,
        capability="assistant.answer",
        has_side_effects=True,
    ) is VerificationLevel.ACTION


def test_model_self_confidence_cannot_lower_verification_level() -> None:
    policy = VerificationPolicy()

    low_confidence = policy.select_level(
        risk_class=RiskClass.HIGH,
        capability="assistant.answer",
        model_self_confidence=0.01,
    )
    high_confidence = policy.select_level(
        risk_class=RiskClass.HIGH,
        capability="assistant.answer",
        model_self_confidence=0.999,
    )

    assert low_confidence is VerificationLevel.ACTION
    assert high_confidence is VerificationLevel.ACTION


def test_evidence_claim_with_valid_bound_citation_verifies() -> None:
    evidence = _evidence()
    claim = Claim(
        claim_id="claim-1",
        text="The fact is supported.",
        kind=ClaimKind.FACTUAL,
        evidence_refs=("ev-1",),
        citation_refs=("cite-1",),
    )

    receipt = VerificationRuntime().verify_deterministic(
        _request(VerificationLevel.EVIDENCE),
        DeterministicVerificationInput(
            candidate_text="Answer with citation.",
            claims=(claim,),
            evidence=(evidence,),
            evidence_content={"ev-1": "supported fact"},
        ),
        now=_now(),
    )

    assert receipt.outcome is VerificationOutcome.VERIFIED
    assert receipt.claim_checks[0].grounded is True
    assert receipt.claim_checks[0].citation_valid is True


def test_evidence_digest_tamper_is_detected_and_qualified() -> None:
    evidence = _evidence()
    claim = Claim(
        claim_id="claim-1",
        text="The fact is supported.",
        evidence_refs=("ev-1",),
        citation_refs=("cite-1",),
    )

    receipt = VerificationRuntime().verify_deterministic(
        _request(VerificationLevel.EVIDENCE),
        DeterministicVerificationInput(
            candidate_text="Answer",
            claims=(claim,),
            evidence=(evidence,),
            evidence_content={"ev-1": "tampered content"},
        ),
        now=_now(),
    )

    assert receipt.outcome is VerificationOutcome.QUALIFIED
    assert "evidence_digest_mismatch" in receipt.claim_checks[0].reason_codes
    assert "claim_grounding_or_citation_failed" in receipt.reason_codes


def test_citation_must_bind_to_claim_evidence_not_global_evidence() -> None:
    first = _evidence("ev-1", citation_id="cite-1")
    second = _evidence("ev-2", content="other", citation_id="cite-2")
    claim = Claim(
        claim_id="claim-1",
        text="Claim cites wrong source.",
        evidence_refs=("ev-1",),
        citation_refs=("cite-2",),
    )

    receipt = VerificationRuntime().verify_deterministic(
        _request(
            VerificationLevel.EVIDENCE,
            evidence_refs=("ev-1", "ev-2"),
        ),
        DeterministicVerificationInput(
            candidate_text="Answer",
            claims=(claim,),
            evidence=(first, second),
        ),
        now=_now(),
    )

    assert receipt.outcome is VerificationOutcome.QUALIFIED
    assert receipt.claim_checks[0].citation_valid is False
    assert (
        "citation_not_bound_to_claim_evidence"
        in receipt.claim_checks[0].reason_codes
    )


def test_action_level_blocks_failed_postcondition() -> None:
    evidence = _evidence()
    claim = Claim(
        claim_id="claim-1",
        text="Action result is supported.",
        evidence_refs=("ev-1",),
    )
    postcondition = PostconditionCheck(
        check_id="post-1",
        subject_ref="tool-receipt:1",
        passed=False,
        reason_code="expected_state_missing",
    )

    receipt = VerificationRuntime().verify_deterministic(
        _request(
            VerificationLevel.ACTION,
            tool_receipt_refs=("tool-receipt:1",),
        ),
        DeterministicVerificationInput(
            candidate_text="Action complete",
            claims=(claim,),
            evidence=(evidence,),
            postconditions=(postcondition,),
        ),
        now=_now(),
    )

    assert receipt.outcome is VerificationOutcome.BLOCK
    assert "action_postcondition_failed" in receipt.reason_codes


def test_tool_receipt_adapter_uses_observable_status_only() -> None:
    succeeded = ToolExecutionReceipt(
        receipt_id=str(uuid4()),
        request_id=str(uuid4()),
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="k",
        arguments_digest="a" * 64,
        status=ToolExecutionStatus.SUCCEEDED,
        started_at=_now(),
        finished_at=_now(),
        result_ref="artifact:1",
    )
    failed = ToolExecutionReceipt(
        receipt_id=str(uuid4()),
        request_id=str(uuid4()),
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="k2",
        arguments_digest="b" * 64,
        status=ToolExecutionStatus.FAILED,
        started_at=_now(),
        finished_at=_now(),
        error_code="RuntimeError",
    )

    assert tool_receipt_postcondition(succeeded).passed is True
    assert tool_receipt_postcondition(failed).passed is False


def test_high_impact_cannot_be_deterministically_promoted_without_semantic_verifier() -> None:
    evidence = _evidence()
    claim = Claim(
        claim_id="claim-1",
        text="High-impact claim.",
        evidence_refs=("ev-1",),
        citation_refs=("cite-1",),
    )

    receipt = VerificationRuntime().verify_deterministic(
        _request(VerificationLevel.HIGH_IMPACT),
        DeterministicVerificationInput(
            candidate_text="High-impact answer",
            claims=(claim,),
            evidence=(evidence,),
        ),
        now=_now(),
    )

    assert receipt.outcome is VerificationOutcome.BLOCK
    assert receipt.repair_directive == {
        "reason": "semantic_high_impact_verifier_required",
        "retry_allowed": False,
    }


def test_expired_verification_deadline_does_not_verify() -> None:
    receipt = VerificationRuntime().verify_deterministic(
        _request(
            VerificationLevel.STRUCTURAL,
            evidence_refs=(),
            deadline=_now() - timedelta(seconds=1),
        ),
        DeterministicVerificationInput(candidate_text="candidate"),
        now=_now(),
    )

    assert receipt.outcome is VerificationOutcome.REPAIR
    assert "verification_deadline_expired" in receipt.reason_codes



class _SemanticVerifier:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    async def verify(self, request, verification_input):
        self.calls += 1
        if not self.decisions:
            raise RuntimeError("no decision")
        decision = self.decisions.pop(0)
        if isinstance(decision, Exception):
            raise decision
        return decision


def _semantic_decision(
    outcome: VerificationOutcome,
    *,
    reasons=("semantic_check",),
    confidence=ConfidenceBand.HIGH,
    repair_instruction=None,
):
    return SemanticVerificationDecision(
        outcome=outcome,
        reason_codes=tuple(reasons),
        confidence_band=confidence,
        route_ref="provider:test:resp-1",
        repair_instruction=repair_instruction,
    )


@pytest.mark.asyncio
async def test_high_impact_semantic_verifier_can_promote_after_deterministic_pass() -> None:
    evidence = _evidence()
    claim = Claim(
        claim_id="claim-1",
        text="High-impact claim.",
        evidence_refs=("ev-1",),
        citation_refs=("cite-1",),
    )
    verifier = _SemanticVerifier(
        [_semantic_decision(VerificationOutcome.VERIFIED)]
    )

    result = await verify_with_semantic(
        VerificationRuntime(),
        _request(VerificationLevel.HIGH_IMPACT),
        DeterministicVerificationInput(
            candidate_text="High-impact answer",
            claims=(claim,),
            evidence=(evidence,),
        ),
        semantic_verifier=verifier,
        now=_now(),
    )

    assert result.receipt.outcome is VerificationOutcome.VERIFIED
    assert result.receipt.verifier_route_refs == ("provider:test:resp-1",)
    assert result.receipt.confidence_band is ConfidenceBand.HIGH
    assert verifier.calls == 1


@pytest.mark.asyncio
async def test_semantic_high_confidence_cannot_override_explicit_block() -> None:
    evidence = _evidence()
    claim = Claim(
        claim_id="claim-1",
        text="High-impact claim.",
        evidence_refs=("ev-1",),
        citation_refs=("cite-1",),
    )
    verifier = _SemanticVerifier(
        [
            _semantic_decision(
                VerificationOutcome.BLOCK,
                reasons=("unsupported_high_impact_claim",),
                confidence=ConfidenceBand.HIGH,
            )
        ]
    )

    result = await verify_with_semantic(
        VerificationRuntime(),
        _request(VerificationLevel.HIGH_IMPACT),
        DeterministicVerificationInput(
            candidate_text="High-impact answer",
            claims=(claim,),
            evidence=(evidence,),
        ),
        semantic_verifier=verifier,
        now=_now(),
    )

    assert result.receipt.outcome is VerificationOutcome.BLOCK
    assert result.receipt.confidence_band is ConfidenceBand.HIGH
    assert "unsupported_high_impact_claim" in result.receipt.reason_codes


@pytest.mark.asyncio
async def test_semantic_verifier_failure_blocks_high_impact() -> None:
    evidence = _evidence()
    claim = Claim(
        claim_id="claim-1",
        text="High-impact claim.",
        evidence_refs=("ev-1",),
        citation_refs=("cite-1",),
    )
    verifier = _SemanticVerifier([RuntimeError("provider unavailable")])

    result = await verify_with_semantic(
        VerificationRuntime(),
        _request(VerificationLevel.HIGH_IMPACT),
        DeterministicVerificationInput(
            candidate_text="High-impact answer",
            claims=(claim,),
            evidence=(evidence,),
        ),
        semantic_verifier=verifier,
        now=_now(),
    )

    assert result.receipt.outcome is VerificationOutcome.BLOCK
    assert "semantic_verifier_failed" in result.receipt.reason_codes


@pytest.mark.asyncio
async def test_semantic_repair_is_bounded_and_records_lineage() -> None:
    evidence = _evidence()
    claim = Claim(
        claim_id="claim-1",
        text="High-impact claim.",
        evidence_refs=("ev-1",),
        citation_refs=("cite-1",),
    )
    verifier = _SemanticVerifier(
        [
            _semantic_decision(
                VerificationOutcome.REPAIR,
                reasons=("wording_needs_repair",),
                repair_instruction="Use more precise wording.",
            ),
            _semantic_decision(
                VerificationOutcome.VERIFIED,
                reasons=("repaired_candidate_verified",),
            ),
        ]
    )
    repair_calls = []

    async def repair(candidate, instruction, attempt):
        repair_calls.append((candidate, instruction, attempt))
        return "Repaired high-impact answer"

    result = await verify_with_semantic(
        VerificationRuntime(),
        _request(VerificationLevel.HIGH_IMPACT),
        DeterministicVerificationInput(
            candidate_text="Original high-impact answer",
            claims=(claim,),
            evidence=(evidence,),
        ),
        semantic_verifier=verifier,
        repair_callback=repair,
        now=_now(),
    )

    assert result.receipt.outcome is VerificationOutcome.VERIFIED
    assert result.candidate_text == "Repaired high-impact answer"
    assert len(result.repair_lineage) == 1
    assert result.repair_lineage[0].parent_candidate_ref == "candidate:1"
    assert result.repair_lineage[0].repaired_candidate_ref == "candidate:1:repair:1"
    assert repair_calls[0][2] == 1
    assert verifier.calls == 2


@pytest.mark.asyncio
async def test_semantic_repair_budget_exhaustion_blocks() -> None:
    evidence = _evidence()
    claim = Claim(
        claim_id="claim-1",
        text="High-impact claim.",
        evidence_refs=("ev-1",),
        citation_refs=("cite-1",),
    )
    verifier = _SemanticVerifier(
        [
            _semantic_decision(
                VerificationOutcome.REPAIR,
                repair_instruction="Repair it.",
            ),
            _semantic_decision(
                VerificationOutcome.REPAIR,
                repair_instruction="Repair again.",
            ),
        ]
    )

    async def repair(candidate, instruction, attempt):
        return candidate + " repaired"

    result = await verify_with_semantic(
        VerificationRuntime(),
        _request(VerificationLevel.HIGH_IMPACT),
        DeterministicVerificationInput(
            candidate_text="Original",
            claims=(claim,),
            evidence=(evidence,),
        ),
        semantic_verifier=verifier,
        repair_callback=repair,
        now=_now(),
    )

    assert result.receipt.outcome is VerificationOutcome.BLOCK
    assert "repair_budget_exhausted" in result.receipt.reason_codes
    assert len(result.repair_lineage) == 1


@pytest.mark.asyncio
async def test_canonical_provider_semantic_verifier_requests_structured_no_tools() -> None:
    captured = {}

    class FakeResponse:
        provider = "openai"
        request_id = "req-1"
        response_id = "resp-1"
        structured_output = {
            "outcome": "verified",
            "reason_codes": ["supported"],
            "confidence_band": "medium",
            "repair_instruction": None,
        }

    class FakeProvider:
        async def generate(self, request):
            captured["request"] = request
            return FakeResponse()

    evidence = _evidence()
    claim = Claim(
        claim_id="claim-1",
        text="Claim.",
        evidence_refs=("ev-1",),
    )
    verifier = CanonicalProviderSemanticVerifier(FakeProvider())

    decision = await verifier.verify(
        _request(VerificationLevel.HIGH_IMPACT),
        DeterministicVerificationInput(
            candidate_text="Candidate",
            claims=(claim,),
            evidence=(evidence,),
            evidence_content={"ev-1": "supported fact"},
        ),
    )

    assert decision.outcome is VerificationOutcome.VERIFIED
    assert decision.route_ref == "provider:openai:resp-1"
    request = captured["request"]
    assert request.purpose == "verification"
    assert request.tool_choice == "none"
    assert request.structured_output_schema["type"] == "object"
