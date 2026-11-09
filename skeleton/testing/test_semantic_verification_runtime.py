from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from uuid import uuid4

import pytest

from skeleton.contracts.verification import (
    ClaimKind,
    ClaimScope,
    EvidenceProducer,
    EvidenceReference,
    EvidenceRelation,
    PostconditionObservation,
    VerificationClaim,
    VerificationRisk,
)
from skeleton.intelligence.verification_runtime import (
    FinalizationDisposition,
    SemanticVerificationRuntime,
)
from skeleton.provider_runtime import (
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
)


NOW = datetime(2026, 9, 24, 4, 0, tzinfo=timezone.utc)


class FakeAdapter(ProviderAdapter):
    provider_id = "fake-provider"
    model = "fake-model"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    @property
    def available(self):
        return True

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        output = self.outputs.pop(0)
        return ProviderResponse(
            text=None,
            provider=self.provider_id,
            model=self.model,
            request_id=f"req-{len(self.requests)}",
            structured_output=output,
        )


def _claim(*, risk=VerificationRisk.HIGH, kind=ClaimKind.FACT, operation_id=None):
    return VerificationClaim(
        claim_id=str(uuid4()),
        tenant_id="tenant-a",
        text="Deployment is healthy.",
        kind=kind,
        risk=risk,
        created_at=NOW,
        scope=ClaimScope(environment="production"),
        operation_id=operation_id,
        generated_by_model=True,
    )


def _evidence(claim, *, origin, source, text):
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
        scope=ClaimScope(environment="production"),
        provenance_refs=("source-ledger:" + origin,),
    )


def _materialized(*items):
    return {item[0].evidence_id: item[1] for item in items}


@pytest.mark.asyncio
async def test_high_risk_claim_publishes_only_after_independent_semantic_pass():
    claim = _claim()
    one_text = "Health probe reports all replicas ready."
    two_text = "Deployment controller reports desired equals available replicas."
    one = _evidence(claim, origin="probe", source="health", text=one_text)
    two = _evidence(claim, origin="controller", source="deploy", text=two_text)
    adapter = FakeAdapter([
        {"verdict": "pass", "issues": [], "confidence": 0.01},
    ])

    result = await SemanticVerificationRuntime(adapter).finalize(
        claim,
        evidence=(one, two),
        evidence_text=_materialized((one, one_text), (two, two_text)),
        verified_at=NOW,
    )

    assert result.disposition is FinalizationDisposition.PUBLISH
    assert result.independent_check is not None
    assert result.independent_check.independent is True
    assert result.independent_check.confidence == 0.01
    assert result.final_assessment.policy_satisfied is True
    assert len(adapter.requests) == 1
    assert adapter.requests[0].purpose == "semantic-verification"
    assert adapter.requests[0].tools == ()


@pytest.mark.asyncio
async def test_high_impact_qualify_is_block_not_soft_publish():
    claim = _claim()
    a_text = "Primary probe is healthy."
    b_text = "Independent deployment state is healthy."
    a = _evidence(claim, origin="a", source="a", text=a_text)
    b = _evidence(claim, origin="b", source="b", text=b_text)
    adapter = FakeAdapter([
        {"verdict": "qualify", "issues": ["one zone has not reported"]},
    ])
    result = await SemanticVerificationRuntime(adapter).finalize(
        claim,
        evidence=(a, b),
        evidence_text=_materialized((a, a_text), (b, b_text)),
        verified_at=NOW,
    )
    assert result.disposition is FinalizationDisposition.BLOCK


@pytest.mark.asyncio
async def test_lower_risk_force_semantic_can_qualify_or_abstain():
    claim = _claim(risk=VerificationRisk.MEDIUM)
    text = "One scoped primary source supports the claim."
    evidence = _evidence(claim, origin="primary", source="primary", text=text)

    qualify = FakeAdapter([
        {"verdict": "qualify", "issues": ["limited to production"]},
    ])
    qualified = await SemanticVerificationRuntime(qualify).finalize(
        claim,
        evidence=(evidence,),
        evidence_text=_materialized((evidence, text)),
        verified_at=NOW,
        force_semantic=True,
    )
    assert qualified.disposition is FinalizationDisposition.QUALIFIED

    abstain = FakeAdapter([
        {"verdict": "abstain", "issues": ["semantic ambiguity remains"]},
    ])
    abstained = await SemanticVerificationRuntime(abstain).finalize(
        claim,
        evidence=(evidence,),
        evidence_text=_materialized((evidence, text)),
        verified_at=NOW,
        force_semantic=True,
    )
    assert abstained.disposition is FinalizationDisposition.ABSTAIN


@pytest.mark.asyncio
async def test_repair_lineage_is_bounded_and_requires_regrounding_before_publish():
    claim = _claim(risk=VerificationRisk.MEDIUM)
    text = "Deployment controller reports 9 of 10 replicas ready."
    evidence = _evidence(claim, origin="controller", source="deploy", text=text)
    adapter = FakeAdapter([
        {
            "verdict": "repair",
            "issues": ["claim overstates health"],
            "revised_claim": "Deployment has 9 of 10 replicas ready.",
            "confidence": 0.99,
        },
        {"verdict": "pass", "issues": [], "confidence": 1.0},
    ])
    result = await SemanticVerificationRuntime(
        adapter,
        max_rounds=2,
        max_repairs=1,
    ).finalize(
        claim,
        evidence=(evidence,),
        evidence_text=_materialized((evidence, text)),
        verified_at=NOW,
        force_semantic=True,
    )
    assert result.disposition is FinalizationDisposition.QUALIFIED
    assert result.final_claim.claim_id != claim.claim_id
    assert result.final_claim.text == "Deployment has 9 of 10 replicas ready."
    assert len(result.repair_lineage) == 1
    assert result.repair_lineage[0].original_claim_id == claim.claim_id
    assert "repaired_claim_requires_citation_rebinding" in result.issues


@pytest.mark.asyncio
async def test_self_reported_confidence_cannot_bypass_missing_independent_origin():
    claim = _claim()
    text = "Only one source is available."
    evidence = _evidence(claim, origin="single", source="mirror", text=text)
    adapter = FakeAdapter([
        {"verdict": "pass", "issues": [], "confidence": 1.0},
    ])
    result = await SemanticVerificationRuntime(adapter).finalize(
        claim,
        evidence=(evidence,),
        evidence_text=_materialized((evidence, text)),
        verified_at=NOW,
    )
    assert result.disposition is FinalizationDisposition.BLOCK
    assert len(adapter.requests) == 0
    assert "independent_origin_requirement_unsatisfied" in result.issues


@pytest.mark.asyncio
async def test_critical_action_stays_blocked_until_postcondition_is_observed():
    operation_id = str(uuid4())
    claim = _claim(
        risk=VerificationRisk.CRITICAL,
        kind=ClaimKind.ACTION_OUTCOME,
        operation_id=operation_id,
    )
    one_text = "Write API returned committed."
    two_text = "Read-after-write observed expected state."
    one = _evidence(claim, origin="write", source="write-api", text=one_text)
    two = _evidence(claim, origin="read", source="read-api", text=two_text)

    blocked_adapter = FakeAdapter([
        {"verdict": "pass", "issues": [], "confidence": 1.0},
    ])
    blocked = await SemanticVerificationRuntime(blocked_adapter).finalize(
        claim,
        evidence=(one, two),
        evidence_text=_materialized((one, one_text), (two, two_text)),
        verified_at=NOW,
        action_effect="irreversible",
        externally_observable_action=True,
    )
    assert blocked.disposition is FinalizationDisposition.BLOCK
    assert "postcondition_observation_required" in blocked.issues

    observation = PostconditionObservation(
        observation_id=str(uuid4()),
        postcondition_id=str(uuid4()),
        operation_id=operation_id,
        tenant_id=claim.tenant_id,
        observed_at=NOW,
        passed=True,
        evidence_ids=(two.evidence_id,),
    )
    pass_adapter = FakeAdapter([
        {"verdict": "pass", "issues": [], "confidence": 0.2},
    ])
    published = await SemanticVerificationRuntime(pass_adapter).finalize(
        claim,
        evidence=(one, two),
        evidence_text=_materialized((one, one_text), (two, two_text)),
        postconditions=(observation,),
        verified_at=NOW,
        action_effect="irreversible",
        externally_observable_action=True,
    )
    assert published.disposition is FinalizationDisposition.PUBLISH
    assert published.final_assessment.policy_satisfied is True


@pytest.mark.asyncio
async def test_evidence_digest_mismatch_fails_closed_before_provider():
    claim = _claim()
    text = "Real evidence."
    one = _evidence(claim, origin="one", source="one", text=text)
    two = _evidence(claim, origin="two", source="two", text="Second evidence.")
    adapter = FakeAdapter([
        {"verdict": "pass", "issues": [], "confidence": 1.0},
    ])
    result = await SemanticVerificationRuntime(adapter).finalize(
        claim,
        evidence=(one, two),
        evidence_text={
            one.evidence_id: "tampered evidence",
            two.evidence_id: "Second evidence.",
        },
        verified_at=NOW,
    )
    assert result.disposition is FinalizationDisposition.BLOCK
    assert len(adapter.requests) == 0
    assert "semantic verification evidence digest mismatch" in result.issues
