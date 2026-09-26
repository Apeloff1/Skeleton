from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
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
from skeleton.intelligence.verification_runtime import (
    FinalizationDisposition,
    SemanticVerificationRuntime,
    VerificationRuntime,
    materialize_verification_receipt,
)
from skeleton.provider_runtime import (
    ProviderAdapter,
    ProviderResponse,
    ProviderUnavailableError,
)
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

def test_materialized_verification_receipt_is_deterministic_and_observable() -> None:
    claim = _claim()
    evidence = _evidence(claim, origin="primary-1", source="primary")
    assessment = VerificationRuntime().verify(
        claim,
        evidence=(evidence,),
        verified_at=NOW,
        verifier_id="verification-runtime:test",
    )

    first = materialize_verification_receipt(
        claim,
        assessment,
        execution_id="exec-1",
        result_ref="execution-result:exec-1",
    )
    replay = materialize_verification_receipt(
        claim,
        assessment,
        execution_id="exec-1",
        result_ref="execution-result:exec-1",
    )

    assert replay == first
    assert first.policy_satisfied is True
    assert first.outcome is VerificationOutcome.PASSED
    assert first.supporting_evidence_ids == (evidence.evidence_id,)
    assert first.execution_id == "exec-1"
    assert first.result_ref == "execution-result:exec-1"
    assert first.check_id == assessment.check.check_id

    payload = first.as_dict()
    assert payload["receipt_id"] == first.receipt_id
    assert payload["claim_digest"] == claim.digest
    assert payload["verified_at"] == NOW.isoformat()
    serialized_keys = " ".join(sorted(payload))
    assert "chain_of_thought" not in serialized_keys
    assert "reasoning_text" not in serialized_keys
    assert "hidden_reasoning" not in serialized_keys



class _SemanticAdapter(ProviderAdapter):
    provider_id = "semantic-test"
    model = "verifier-v1"

    def __init__(self, responses=(), *, error=None):
        self.responses = list(responses)
        self.error = error
        self.requests = []

    @property
    def available(self) -> bool:
        return True

    async def generate(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AssertionError("unexpected semantic verifier request")
        return self.responses.pop(0)


def _semantic_response(
    verdict: str,
    *,
    issues=(),
    revised_claim=None,
    confidence=None,
    request_id="semantic-request-1",
):
    payload = {
        "verdict": verdict,
        "issues": list(issues),
    }
    if revised_claim is not None:
        payload["revised_claim"] = revised_claim
    if confidence is not None:
        payload["confidence"] = confidence
    return ProviderResponse(
        text=None,
        provider="semantic-test",
        model="verifier-v1",
        request_id=request_id,
        structured_output=payload,
    )


def _semantic_evidence(
    claim,
    *,
    origin: str,
    source: str,
    text: str,
):
    return EvidenceReference(
        evidence_id=str(uuid4()),
        claim_id=claim.claim_id,
        tenant_id=claim.tenant_id,
        source_id=source,
        origin_id=origin,
        content_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        locator="line:1",
        relation=EvidenceRelation.SUPPORTS,
        producer=EvidenceProducer.SOURCE,
        observed_at=NOW,
        scope=claim.scope,
        provenance_refs=("source-ledger:" + origin,),
    )


@pytest.mark.asyncio
async def test_semantic_verifier_uses_provider_neutral_structured_request_and_publishes_high_risk_pass():
    claim = _claim(risk=VerificationRisk.HIGH)
    first_text = "Deployment health check passed in staging."
    second_text = "Independent staging monitor reports healthy."
    first = _semantic_evidence(
        claim,
        origin="origin-1",
        source="health-api",
        text=first_text,
    )
    second = _semantic_evidence(
        claim,
        origin="origin-2",
        source="independent-monitor",
        text=second_text,
    )
    adapter = _SemanticAdapter(
        [
            _semantic_response(
                "pass",
                confidence=0.97,
                request_id="semantic-pass-1",
            )
        ]
    )

    result = await SemanticVerificationRuntime(adapter).finalize(
        claim,
        evidence=(first, second),
        evidence_text={
            first.evidence_id: first_text,
            second.evidence_id: second_text,
        },
        verified_at=NOW,
    )

    assert result.disposition is FinalizationDisposition.PUBLISH
    assert result.final_assessment.policy_satisfied is True
    assert result.independent_check is not None
    assert result.independent_check.independent is True
    assert result.independent_check.level is VerificationLevel.INDEPENDENT
    assert result.independent_check.evidence_ids == (
        first.evidence_id,
        second.evidence_id,
    )
    assert len(adapter.requests) == 1
    request = adapter.requests[0]
    assert request.purpose == "semantic-verification"
    assert request.tenant_id == claim.tenant_id
    assert request.tool_choice == "none"
    assert request.tools == ()
    assert request.max_output_tokens == 800
    assert request.structured_output_schema["additionalProperties"] is False
    assert request.structured_output_schema["properties"]["verdict"]["enum"] == [
        "pass",
        "repair",
        "qualify",
        "abstain",
        "block",
    ]
    assert first_text in request.prompt
    assert second_text in request.prompt
    assert "chain_of_thought" not in request.prompt
    assert "hidden_reasoning" not in request.prompt


@pytest.mark.asyncio
async def test_semantic_verifier_outage_abstains_low_risk_but_blocks_high_risk():
    outage = ProviderUnavailableError("semantic verifier unavailable")
    low_adapter = _SemanticAdapter(error=outage)
    low = _claim(
        risk=VerificationRisk.LOW,
        kind=ClaimKind.HYPOTHESIS,
    )

    low_result = await SemanticVerificationRuntime(low_adapter).finalize(
        low,
        verified_at=NOW,
        force_semantic=True,
    )

    assert low_result.disposition is FinalizationDisposition.ABSTAIN
    assert "semantic_verifier_unavailable_or_invalid" in low_result.issues
    assert len(low_adapter.requests) == 1

    high = _claim(risk=VerificationRisk.HIGH)
    first_text = "Primary authority reports healthy."
    second_text = "Independent authority reports healthy."
    first = _semantic_evidence(
        high,
        origin="origin-a",
        source="primary-authority",
        text=first_text,
    )
    second = _semantic_evidence(
        high,
        origin="origin-b",
        source="secondary-authority",
        text=second_text,
    )
    high_adapter = _SemanticAdapter(
        error=ProviderUnavailableError("semantic verifier unavailable")
    )

    high_result = await SemanticVerificationRuntime(high_adapter).finalize(
        high,
        evidence=(first, second),
        evidence_text={
            first.evidence_id: first_text,
            second.evidence_id: second_text,
        },
        verified_at=NOW,
    )

    assert high_result.disposition is FinalizationDisposition.BLOCK
    assert "semantic_verifier_unavailable_or_invalid" in high_result.issues
    assert len(high_adapter.requests) == 1


@pytest.mark.asyncio
async def test_semantic_repair_preserves_lineage_and_requires_citation_rebinding_before_publish():
    claim = _claim()
    evidence_text = "The staging deployment is healthy with one degraded replica."
    evidence = _semantic_evidence(
        claim,
        origin="origin-1",
        source="deployment-status",
        text=evidence_text,
    )
    adapter = _SemanticAdapter(
        [
            _semantic_response(
                "repair",
                issues=("claim is too absolute",),
                revised_claim=(
                    "Deployment is healthy in staging with one degraded replica."
                ),
                request_id="semantic-repair-1",
            ),
            _semantic_response(
                "pass",
                confidence=0.91,
                request_id="semantic-repair-2",
            ),
        ]
    )

    result = await SemanticVerificationRuntime(
        adapter,
        max_rounds=2,
        max_repairs=1,
    ).finalize(
        claim,
        evidence=(evidence,),
        evidence_text={evidence.evidence_id: evidence_text},
        verified_at=NOW,
        force_semantic=True,
    )

    assert result.disposition is FinalizationDisposition.QUALIFIED
    assert result.final_claim.claim_id != claim.claim_id
    assert result.final_claim.text.endswith("one degraded replica.")
    assert result.final_claim.generated_by_model is True
    assert len(result.repair_lineage) == 1
    lineage = result.repair_lineage[0]
    assert lineage.original_claim_id == claim.claim_id
    assert lineage.repaired_claim_id == result.final_claim.claim_id
    assert lineage.original_claim_digest == claim.digest
    assert lineage.repaired_claim_digest == result.final_claim.digest
    assert "repaired_claim_requires_citation_rebinding" in result.issues
    assert len(adapter.requests) == 2


@pytest.mark.asyncio
async def test_high_impact_repaired_claim_is_blocked_until_evidence_is_rebound():
    claim = _claim(risk=VerificationRisk.HIGH)
    first_text = "Primary deployment authority reports healthy."
    second_text = "Independent deployment authority reports healthy."
    first = _semantic_evidence(
        claim,
        origin="origin-1",
        source="primary",
        text=first_text,
    )
    second = _semantic_evidence(
        claim,
        origin="origin-2",
        source="secondary",
        text=second_text,
    )
    adapter = _SemanticAdapter(
        [
            _semantic_response(
                "repair",
                issues=("scope needs qualification",),
                revised_claim="Deployment is healthy in staging.",
                request_id="repair-high-1",
            ),
            _semantic_response(
                "pass",
                request_id="repair-high-2",
            ),
        ]
    )

    result = await SemanticVerificationRuntime(
        adapter,
        max_rounds=2,
        max_repairs=1,
    ).finalize(
        claim,
        evidence=(first, second),
        evidence_text={
            first.evidence_id: first_text,
            second.evidence_id: second_text,
        },
        verified_at=NOW,
    )

    assert result.disposition is FinalizationDisposition.BLOCK
    assert len(result.repair_lineage) == 1
    assert "repaired_claim_requires_citation_rebinding" in result.issues


@pytest.mark.asyncio
async def test_semantic_repair_budget_is_bounded_and_fails_safe():
    claim = _claim()
    evidence_text = "Deployment is healthy in staging."
    evidence = _semantic_evidence(
        claim,
        origin="origin-1",
        source="primary",
        text=evidence_text,
    )
    adapter = _SemanticAdapter(
        [
            _semantic_response(
                "repair",
                issues=("first repair",),
                revised_claim="Deployment appears healthy in staging.",
                request_id="repair-budget-1",
            ),
            _semantic_response(
                "repair",
                issues=("second repair",),
                revised_claim="Deployment is partially healthy in staging.",
                request_id="repair-budget-2",
            ),
        ]
    )

    result = await SemanticVerificationRuntime(
        adapter,
        max_rounds=2,
        max_repairs=1,
    ).finalize(
        claim,
        evidence=(evidence,),
        evidence_text={evidence.evidence_id: evidence_text},
        verified_at=NOW,
        force_semantic=True,
    )

    assert result.disposition is FinalizationDisposition.ABSTAIN
    assert result.issues == ("semantic_repair_budget_exhausted",)
    assert len(result.repair_lineage) == 1
    assert len(adapter.requests) == 2


@pytest.mark.asyncio
async def test_missing_authoritative_evidence_never_invokes_semantic_verifier_even_with_high_confidence():
    claim = _claim(risk=VerificationRisk.HIGH)
    adapter = _SemanticAdapter(
        [
            _semantic_response(
                "pass",
                confidence=1.0,
                request_id="confidence-only",
            )
        ]
    )

    result = await SemanticVerificationRuntime(adapter).finalize(
        claim,
        verified_at=NOW,
        force_semantic=True,
    )

    assert result.disposition is FinalizationDisposition.BLOCK
    assert result.semantic_rounds == ()
    assert adapter.requests == []
    assert "authoritative_support_missing" in result.issues
    assert "semantic_verifier_not_admitted" in result.issues
