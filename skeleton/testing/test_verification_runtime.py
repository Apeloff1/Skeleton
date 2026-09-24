from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from skeleton.contracts.verification import (
    ClaimKind,
    EvidenceKind,
    EvidenceRelation,
    PostconditionState,
    ProvenanceOrigin,
    VerificationBundle,
    VerificationClaim,
    VerificationEvidence,
    VerificationLevel,
)
from skeleton.intelligence.verification_policy import VerificationRequirement
from skeleton.intelligence.verification_runtime import verify_bundle
from skeleton.retrieval.verification import citation_verification_evidence
from skeleton.skills.tool_contract import (
    ToolExecutionReceipt,
    ToolExecutionStatus,
)
from skeleton.skills.verification import (
    tool_postcondition_verification_records,
    tool_receipt_verification_evidence,
)


NOW = datetime(2026, 9, 24, 3, 30, tzinfo=timezone.utc)


def _claim(*, operation=True):
    return VerificationClaim(
        claim_id=str(uuid4()),
        tenant_id="tenant-a",
        text="Deployment is healthy in prod-eu.",
        kind=ClaimKind.ACTION_OUTCOME if operation else ClaimKind.FACT,
        origin_type=ProvenanceOrigin.MODEL,
        origin_ref="provider-result:test",
        asserted_at=NOW,
        operation_id=str(uuid4()) if operation else None,
        context_digest="a" * 64,
        valid_from=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=1),
        population_scope=("service:alpha",),
        environment_scope=("prod-eu",),
    )


def _requirement(**kwargs):
    values = dict(
        level=VerificationLevel.INDEPENDENT,
        min_independent_origins=2,
        require_postcondition=False,
        require_fresh_evidence=True,
        require_scope_match=True,
        reasons=("test",),
    )
    values.update(kwargs)
    return VerificationRequirement(**values)


def _citation(claim, *, origin_id, digest, observed_at=NOW):
    return citation_verification_evidence(
        claim,
        source_id="source:" + digest[:4],
        origin_id=origin_id,
        content_digest=digest,
        observed_at=observed_at,
        locator="page:1",
        provenance_refs=("source-ledger:" + origin_id,),
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=1),
        population_scope=("service:alpha",),
        environment_scope=("prod-eu",),
    )


def test_two_republishers_from_one_origin_do_not_satisfy_independence():
    claim = _claim(operation=False)
    first = _citation(claim, origin_id="wire-a", digest="1" * 64)
    second = _citation(claim, origin_id="wire-a", digest="2" * 64)
    bundle = VerificationBundle(
        bundle_id=str(uuid4()),
        claim=claim,
        evidence=(first, second),
        postconditions=(),
        requested_level=VerificationLevel.INDEPENDENT,
        created_at=NOW,
    )
    result = verify_bundle(bundle, _requirement(), now=NOW)
    assert result.grounding_ok is True
    assert result.independence_ok is False
    assert result.independent_origin_ids == ("wire-a",)
    assert "independent_evidence_insufficient" in result.issue_codes


def test_stale_or_wrong_scope_support_does_not_satisfy_required_evidence():
    claim = _claim(operation=False)
    stale = _citation(
        claim,
        origin_id="primary-a",
        digest="3" * 64,
        observed_at=NOW - timedelta(days=3),
    )
    wrong_scope = VerificationEvidence(
        evidence_id=str(uuid4()),
        tenant_id=claim.tenant_id,
        kind=EvidenceKind.SOURCE,
        origin_type=ProvenanceOrigin.PRIMARY_SOURCE,
        source_id="measurement:b",
        origin_id="measurement:b",
        content_digest="4" * 64,
        observed_at=NOW,
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=1),
        population_scope=("service:beta",),
        environment_scope=("staging",),
        provenance_refs=("measurement-ledger:b",),
        bound_claim_ids=(claim.claim_id,),
        relation=EvidenceRelation.SUPPORTS,
    )
    bundle = VerificationBundle(
        bundle_id=str(uuid4()),
        claim=claim,
        evidence=(stale, wrong_scope),
        postconditions=(),
        requested_level=VerificationLevel.GROUNDED,
        created_at=NOW,
    )
    result = verify_bundle(
        bundle,
        _requirement(
            level=VerificationLevel.GROUNDED,
            min_independent_origins=1,
        ),
        now=NOW,
        max_evidence_age_seconds=3600,
    )
    assert result.scope_ok is True
    assert result.freshness_ok is False
    assert "fresh_supporting_evidence_missing" in result.issue_codes


def test_uninspectable_citation_fails_integrity_even_if_marked_supporting():
    claim = _claim(operation=False)
    evidence = VerificationEvidence(
        evidence_id=str(uuid4()),
        tenant_id=claim.tenant_id,
        kind=EvidenceKind.CITATION,
        origin_type=ProvenanceOrigin.PRIMARY_SOURCE,
        source_id="source:a",
        origin_id="origin:a",
        content_digest="5" * 64,
        observed_at=NOW,
        bound_claim_ids=(claim.claim_id,),
        relation=EvidenceRelation.SUPPORTS,
    )
    bundle = VerificationBundle(
        bundle_id=str(uuid4()),
        claim=claim,
        evidence=(evidence,),
        postconditions=(),
        requested_level=VerificationLevel.GROUNDED,
        created_at=NOW,
    )
    result = verify_bundle(
        bundle,
        _requirement(
            level=VerificationLevel.GROUNDED,
            min_independent_origins=1,
            require_fresh_evidence=False,
            require_scope_match=False,
        ),
        now=NOW,
    )
    assert result.citation_integrity_ok is False
    assert "citation_integrity_failed" in result.issue_codes


def _receipt(claim, *, status=ToolExecutionStatus.SUCCEEDED, compensation_ref=None):
    return ToolExecutionReceipt(
        receipt_id=str(uuid4()),
        request_id=str(uuid4()),
        operation_id=claim.operation_id,
        tenant_id=claim.tenant_id,
        tool_id="deploy.apply",
        idempotency_key="deploy-1",
        arguments_digest="6" * 64,
        status=status,
        started_at=NOW - timedelta(seconds=2),
        finished_at=NOW - timedelta(seconds=1),
        result_ref="result:deploy" if status is ToolExecutionStatus.SUCCEEDED else None,
        error_code=None if status is ToolExecutionStatus.SUCCEEDED else "failed",
        compensation_ref=compensation_ref,
    )


def test_tool_receipt_success_alone_does_not_prove_action_postcondition():
    claim = _claim()
    receipt = _receipt(claim)
    receipt_evidence = tool_receipt_verification_evidence(claim, receipt)
    bundle = VerificationBundle(
        bundle_id=str(uuid4()),
        claim=claim,
        evidence=(receipt_evidence,),
        postconditions=(),
        requested_level=VerificationLevel.INDEPENDENT,
        created_at=NOW,
    )
    result = verify_bundle(
        bundle,
        _requirement(
            min_independent_origins=0,
            require_postcondition=True,
            require_fresh_evidence=False,
            require_scope_match=False,
        ),
        now=NOW,
    )
    assert result.postcondition_ok is False
    assert "postcondition_missing" in result.issue_codes


def test_independently_observed_satisfied_postcondition_can_close_action_check():
    claim = _claim()
    receipt = _receipt(claim)
    evidence, postcondition = tool_postcondition_verification_records(
        claim,
        receipt,
        state=PostconditionState.SATISFIED,
        observation_digest="7" * 64,
        observation_origin_id="deployment-readback",
        observed_at=NOW,
        subject_ref="deployment:alpha",
    )
    bundle = VerificationBundle(
        bundle_id=str(uuid4()),
        claim=claim,
        evidence=(evidence,),
        postconditions=(postcondition,),
        requested_level=VerificationLevel.GROUNDED,
        created_at=NOW,
    )
    result = verify_bundle(
        bundle,
        _requirement(
            level=VerificationLevel.GROUNDED,
            min_independent_origins=1,
            require_postcondition=True,
            require_fresh_evidence=False,
            require_scope_match=False,
        ),
        now=NOW,
    )
    assert result.postcondition_ok is True
    assert result.grounding_ok is True
    assert result.independence_ok is True
    assert result.satisfied is True


def test_contradiction_is_preserved_instead_of_overwritten():
    claim = _claim(operation=False)
    support = _citation(claim, origin_id="origin-a", digest="8" * 64)
    contradiction = citation_verification_evidence(
        claim,
        source_id="source:b",
        origin_id="origin-b",
        content_digest="9" * 64,
        observed_at=NOW,
        locator="record:2",
        provenance_refs=("source-ledger:b",),
        supports=False,
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=1),
        population_scope=("service:alpha",),
        environment_scope=("prod-eu",),
    )
    bundle = VerificationBundle(
        bundle_id=str(uuid4()),
        claim=claim,
        evidence=(support, contradiction),
        postconditions=(),
        requested_level=VerificationLevel.GROUNDED,
        created_at=NOW,
    )
    result = verify_bundle(
        bundle,
        _requirement(
            level=VerificationLevel.GROUNDED,
            min_independent_origins=1,
        ),
        now=NOW,
    )
    assert result.contradiction_present is True
    assert contradiction.evidence_id in result.contradicting_evidence_ids
    assert "contradictory_evidence_present" in result.issue_codes
