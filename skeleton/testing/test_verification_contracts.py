from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.verification import (
    ClaimKind,
    EvidenceKind,
    PostconditionState,
    ProvenanceOrigin,
    VerificationBundle,
    VerificationClaim,
    VerificationContractError,
    VerificationEvidence,
    VerificationLevel,
    VerificationPostcondition,
)


NOW = datetime(2026, 9, 24, 3, 0, tzinfo=timezone.utc)


def _claim(*, origin=ProvenanceOrigin.MODEL):
    return VerificationClaim(
        claim_id=str(uuid4()),
        tenant_id="tenant-a",
        text="Deployment completed with the requested configuration.",
        kind=ClaimKind.ACTION_OUTCOME,
        origin_type=origin,
        origin_ref="provider-result:test:1",
        asserted_at=NOW,
        operation_id=str(uuid4()),
        context_digest="a" * 64,
        valid_from=NOW,
        population_scope=("deployment:alpha",),
        environment_scope=("prod-eu",),
    )


def _evidence(
    claim,
    *,
    origin_id="origin-a",
    origin_type=ProvenanceOrigin.PRIMARY_SOURCE,
    derived_from=(),
):
    return VerificationEvidence(
        evidence_id=str(uuid4()),
        tenant_id=claim.tenant_id,
        kind=EvidenceKind.SOURCE,
        origin_type=origin_type,
        source_id="source:" + origin_id,
        origin_id=origin_id,
        content_digest="b" * 64,
        observed_at=NOW,
        locator="record:1",
        valid_from=NOW - timedelta(minutes=1),
        population_scope=("deployment:alpha",),
        environment_scope=("prod-eu",),
        provenance_refs=("ledger:source",),
        derived_from_claim_ids=derived_from,
    )


def test_claim_digest_is_scope_sensitive_and_scope_order_is_canonical():
    claim_id = str(uuid4())
    operation_id = str(uuid4())
    common = dict(
        claim_id=claim_id,
        tenant_id="tenant-a",
        text="Latency is below 100 ms.",
        kind=ClaimKind.FACT,
        origin_type=ProvenanceOrigin.PRIMARY_SOURCE,
        origin_ref="measurement:1",
        asserted_at=NOW,
        operation_id=operation_id,
        context_digest="c" * 64,
    )
    first = VerificationClaim(
        **common,
        population_scope=("region:b", "region:a"),
        environment_scope=("prod", "linux"),
    )
    second = VerificationClaim(
        **common,
        population_scope=("region:a", "region:b"),
        environment_scope=("linux", "prod"),
    )
    assert first.claim_digest == second.claim_digest
    changed = VerificationClaim(
        **common,
        population_scope=("region:a",),
        environment_scope=("linux", "prod"),
    )
    assert changed.claim_digest != first.claim_digest


def test_model_and_self_derived_evidence_never_count_as_independent():
    claim = _claim()
    model_evidence = _evidence(
        claim,
        origin_id="same-model",
        origin_type=ProvenanceOrigin.MODEL,
    )
    feedback = _evidence(
        claim,
        origin_id="indexed-summary",
        derived_from=(claim.claim_id,),
    )
    external = _evidence(claim, origin_id="primary-ledger")

    bundle = VerificationBundle(
        bundle_id=str(uuid4()),
        claim=claim,
        evidence=(model_evidence, feedback, external),
        postconditions=(),
        requested_level=VerificationLevel.INDEPENDENT,
        created_at=NOW,
    )
    assert bundle.independent_origin_ids == ("primary-ledger",)


def test_correlated_citations_count_as_one_origin():
    claim = _claim(origin=ProvenanceOrigin.USER)
    first = _evidence(claim, origin_id="wire-service-a")
    second = VerificationEvidence(
        evidence_id=str(uuid4()),
        tenant_id=claim.tenant_id,
        kind=EvidenceKind.CITATION,
        origin_type=ProvenanceOrigin.SECONDARY_SOURCE,
        source_id="republisher:2",
        origin_id="wire-service-a",
        content_digest="d" * 64,
        observed_at=NOW,
        locator="page:2",
    )
    bundle = VerificationBundle(
        bundle_id=str(uuid4()),
        claim=claim,
        evidence=(first, second),
        postconditions=(),
        requested_level=VerificationLevel.INDEPENDENT,
        created_at=NOW,
    )
    assert bundle.independent_origin_ids == ("wire-service-a",)


def test_postcondition_unknown_is_representable_and_satisfied_digest_mismatch_fails():
    claim = _claim()
    evidence = _evidence(claim)
    unknown = VerificationPostcondition(
        postcondition_id=str(uuid4()),
        tenant_id=claim.tenant_id,
        operation_id=claim.operation_id,
        subject_ref="tool:deploy",
        state=PostconditionState.UNKNOWN,
        observed_at=NOW,
        evidence_ids=(evidence.evidence_id,),
        detail_code="provider_timeout_after_submit",
    )
    bundle = VerificationBundle(
        bundle_id=str(uuid4()),
        claim=claim,
        evidence=(evidence,),
        postconditions=(unknown,),
        requested_level=VerificationLevel.HIGH_ASSURANCE,
        created_at=NOW,
    )
    assert bundle.postconditions[0].state is PostconditionState.UNKNOWN

    with pytest.raises(VerificationContractError, match="mismatched"):
        VerificationPostcondition(
            postcondition_id=str(uuid4()),
            tenant_id=claim.tenant_id,
            operation_id=claim.operation_id,
            subject_ref="tool:deploy",
            state=PostconditionState.SATISFIED,
            observed_at=NOW,
            expected_digest="e" * 64,
            actual_digest="f" * 64,
        )


def test_bundle_rejects_cross_tenant_evidence_and_unknown_postcondition_evidence():
    claim = _claim()
    foreign = VerificationEvidence(
        evidence_id=str(uuid4()),
        tenant_id="tenant-b",
        kind=EvidenceKind.SOURCE,
        origin_type=ProvenanceOrigin.PRIMARY_SOURCE,
        source_id="foreign",
        origin_id="foreign-origin",
        content_digest="1" * 64,
        observed_at=NOW,
    )
    with pytest.raises(VerificationContractError, match="tenant mismatch"):
        VerificationBundle(
            bundle_id=str(uuid4()),
            claim=claim,
            evidence=(foreign,),
            postconditions=(),
            requested_level=VerificationLevel.GROUNDED,
            created_at=NOW,
        )

    missing_evidence_id = str(uuid4())
    postcondition = VerificationPostcondition(
        postcondition_id=str(uuid4()),
        tenant_id=claim.tenant_id,
        operation_id=claim.operation_id,
        subject_ref="tool:deploy",
        state=PostconditionState.UNKNOWN,
        observed_at=NOW,
        evidence_ids=(missing_evidence_id,),
    )
    with pytest.raises(VerificationContractError, match="outside verification bundle"):
        VerificationBundle(
            bundle_id=str(uuid4()),
            claim=claim,
            evidence=(),
            postconditions=(postcondition,),
            requested_level=VerificationLevel.GROUNDED,
            created_at=NOW,
        )
