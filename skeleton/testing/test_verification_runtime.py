from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.verification import (
    ClaimKind,
    ClaimScope,
    EvidenceProducer,
    EvidenceReference,
    EvidenceRelation,
    PostconditionSpec,
    VerificationCheck,
    VerificationClaim,
    VerificationLevel,
    VerificationOutcome,
    VerificationRisk,
)
from skeleton.intelligence.verification_runtime import VerificationRuntime
from skeleton.retrieval.verification import ground_claim, validate_citation
from skeleton.skills.tool_contract import (
    ToolExecutionReceipt,
    ToolExecutionStatus,
)
from skeleton.skills.verification import (
    ToolPostconditionError,
    observe_tool_postcondition,
)


NOW = datetime(2026, 9, 24, 3, 30, tzinfo=timezone.utc)


def _claim(
    *,
    risk=VerificationRisk.MEDIUM,
    kind=ClaimKind.FACT,
    generated_by_model=True,
    operation_id=None,
    scope=None,
):
    return VerificationClaim(
        claim_id=str(uuid4()),
        tenant_id="tenant-a",
        text="Deployment is healthy.",
        kind=kind,
        risk=risk,
        created_at=NOW,
        scope=scope or ClaimScope(environment="staging"),
        generated_by_model=generated_by_model,
        operation_id=operation_id,
    )


def _evidence(
    claim,
    *,
    origin,
    source,
    relation=EvidenceRelation.SUPPORTS,
    producer=EvidenceProducer.SOURCE,
    scope=None,
):
    return EvidenceReference(
        evidence_id=str(uuid4()),
        claim_id=claim.claim_id,
        tenant_id=claim.tenant_id,
        source_id=source,
        origin_id=origin,
        content_digest="a" * 64,
        locator="line:1",
        relation=relation,
        producer=producer,
        observed_at=NOW,
        scope=scope or ClaimScope(environment="staging"),
        provenance_refs=("source-ledger:" + origin,),
    )


def test_correlated_mirrors_count_as_one_independent_origin():
    claim = _claim(risk=VerificationRisk.HIGH)
    first = _evidence(claim, origin="origin-1", source="mirror-a")
    second = _evidence(claim, origin="origin-1", source="mirror-b")
    grounding = ground_claim(claim, [first, second])

    assert len(grounding.supporting_evidence_ids) == 2
    assert grounding.supporting_origin_ids == ("origin-1",)

    result = VerificationRuntime().verify(
        claim,
        evidence=(first, second),
        verified_at=NOW,
    )
    assert result.outcome is VerificationOutcome.UNKNOWN
    assert "independent_origin_requirement_unsatisfied" in result.issues


def test_scope_mismatch_citation_is_rejected():
    claim = _claim(
        scope=ClaimScope(
            valid_from=NOW - timedelta(minutes=5),
            environment="production",
            population="eu-users",
        )
    )
    evidence = _evidence(
        claim,
        origin="origin-1",
        source="source-1",
        scope=ClaimScope(
            valid_to=NOW - timedelta(days=1),
            environment="staging",
            population="us-users",
        ),
    )
    result = validate_citation(claim, evidence)
    assert result.accepted is False
    assert "environment_scope_mismatch" in result.reasons
    assert "population_scope_mismatch" in result.reasons
    assert "temporal_scope_stale" in result.reasons


def test_model_evidence_alone_cannot_verify_model_generated_fact():
    claim = _claim()
    model_evidence = _evidence(
        claim,
        origin="same-model",
        source="model-output",
        producer=EvidenceProducer.MODEL,
    )
    result = VerificationRuntime().verify(
        claim,
        evidence=(model_evidence,),
        verified_at=NOW,
    )
    assert result.outcome is VerificationOutcome.UNKNOWN
    assert result.policy_satisfied is False
    assert "authoritative_support_missing" in result.issues


def test_medium_claim_passes_with_one_scoped_external_source():
    claim = _claim()
    evidence = _evidence(claim, origin="primary-1", source="primary")
    result = VerificationRuntime().verify(
        claim,
        evidence=(evidence,),
        verified_at=NOW,
    )
    assert result.outcome is VerificationOutcome.PASSED
    assert result.check is not None
    assert result.check.level is VerificationLevel.EVIDENCE
    assert result.check.evidence_ids == (evidence.evidence_id,)


def test_high_claim_requires_prior_independent_check_even_with_two_origins():
    claim = _claim(risk=VerificationRisk.HIGH)
    one = _evidence(claim, origin="origin-1", source="source-1")
    two = _evidence(claim, origin="origin-2", source="source-2")

    result = VerificationRuntime().verify(
        claim,
        evidence=(one, two),
        verified_at=NOW,
    )
    assert result.outcome is VerificationOutcome.UNKNOWN
    assert "independent_verification_required" in result.issues

    independent = VerificationCheck(
        check_id=str(uuid4()),
        claim_id=claim.claim_id,
        tenant_id=claim.tenant_id,
        level=VerificationLevel.INDEPENDENT,
        outcome=VerificationOutcome.PASSED,
        verifier_id="independent:process-b",
        verified_at=NOW,
        evidence_ids=(one.evidence_id, two.evidence_id),
        independent=True,
    )
    passed = VerificationRuntime().verify(
        claim,
        evidence=(one, two),
        independent_checks=(independent,),
        verified_at=NOW,
    )
    assert passed.outcome is VerificationOutcome.PASSED
    assert passed.check is not None
    assert passed.check.independent is True


def test_authoritative_support_and_contradiction_stays_contested():
    claim = _claim()
    supporting = _evidence(claim, origin="origin-1", source="source-1")
    contradicting = _evidence(
        claim,
        origin="origin-2",
        source="source-2",
        relation=EvidenceRelation.CONTRADICTS,
    )
    result = VerificationRuntime().verify(
        claim,
        evidence=(supporting, contradicting),
        verified_at=NOW,
    )
    assert result.outcome is VerificationOutcome.CONTESTED
    assert result.policy_satisfied is False


def test_tool_postcondition_adapter_never_turns_failed_receipt_into_pass():
    operation_id = str(uuid4())
    spec = PostconditionSpec(
        postcondition_id=str(uuid4()),
        operation_id=operation_id,
        tenant_id="tenant-a",
        description="remote object exists",
        verification_method="read-after-write",
    )
    receipt = ToolExecutionReceipt(
        receipt_id=str(uuid4()),
        request_id=str(uuid4()),
        operation_id=operation_id,
        tenant_id="tenant-a",
        tool_id="repo.write",
        idempotency_key="write-1",
        arguments_digest="b" * 64,
        status=ToolExecutionStatus.FAILED,
        started_at=NOW,
        finished_at=NOW,
        error_code="write_failed",
        metered_tool_calls=1,
    )
    with pytest.raises(ToolPostconditionError, match="cannot satisfy"):
        observe_tool_postcondition(
            spec,
            receipt,
            passed=True,
            observed_at=NOW,
        )

    failed_observation = observe_tool_postcondition(
        spec,
        receipt,
        passed=False,
        observed_at=NOW,
    )
    assert failed_observation.passed is False
    assert failed_observation.result_ref == "tool-receipt:" + receipt.receipt_id
