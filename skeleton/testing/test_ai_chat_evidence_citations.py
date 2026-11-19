from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skeleton.ai.assistant.evidence import (
    ClaimEvidenceBundle,
    ClaimPublicationPolicy,
    EvidenceCitationPlane,
    EvidencePlaneError,
    PublicationDisposition,
    SourceClass,
    SourceQualityProfile,
)
from skeleton.contracts.verification import (
    ClaimKind,
    ClaimScope,
    EvidenceProducer,
    EvidenceReference,
    EvidenceRelation,
    VerificationClaim,
    VerificationRisk,
)
from skeleton.verification.citation_integrity import CitationBinding
from skeleton.verification.claim_identity import ClaimIdentityEngine


NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
CLAIM_ID = "11111111-1111-4111-8111-111111111111"
EVIDENCE_A = "22222222-2222-4222-8222-222222222222"
EVIDENCE_B = "33333333-3333-4333-8333-333333333333"
EVIDENCE_C = "44444444-4444-4444-8444-444444444444"
CONTENT_A = "a" * 64
CONTENT_B = "b" * 64
CONTENT_C = "c" * 64
CLAIM_TEXT = "Algorithm A decreases measured latency by 10 percent."


def claim(
    *,
    risk: VerificationRisk = VerificationRisk.LOW,
    text: str = CLAIM_TEXT,
    scope: ClaimScope | None = None,
) -> VerificationClaim:
    return VerificationClaim(
        claim_id=CLAIM_ID,
        tenant_id="tenant-a",
        text=text,
        kind=ClaimKind.FACT,
        risk=risk,
        created_at=NOW - timedelta(minutes=1),
        scope=scope or ClaimScope(),
        provenance_refs=("generation:receipt-1",),
        generated_by_model=True,
    )


def source(
    source_id: str = "study-a",
    *,
    source_class: SourceClass = SourceClass.PRIMARY,
    quality: float = 0.95,
    provenance: bool = True,
    stable: bool = True,
    accountable: bool = True,
    primary: bool = True,
) -> SourceQualityProfile:
    return SourceQualityProfile(
        source_id=source_id,
        source_class=source_class,
        quality_score=quality,
        provenance_verified=provenance,
        stable_locator=stable,
        accountable_publisher=accountable,
        primary_source=primary,
        policy_ref="source-quality-v1",
    )


def evidence(
    evidence_id: str = EVIDENCE_A,
    *,
    source_id: str = "study-a",
    origin_id: str = "origin-a",
    content_digest: str = CONTENT_A,
    relation: EvidenceRelation = EvidenceRelation.SUPPORTS,
    producer: EvidenceProducer = EvidenceProducer.SOURCE,
    observed_at: datetime | None = None,
    tenant_id: str = "tenant-a",
    claim_id: str = CLAIM_ID,
    scope: ClaimScope | None = None,
    provenance_refs: tuple[str, ...] = ("retrieval:receipt-1",),
) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        claim_id=claim_id,
        tenant_id=tenant_id,
        source_id=source_id,
        origin_id=origin_id,
        content_digest=content_digest,
        locator=f"doi:{source_id}#result",
        relation=relation,
        producer=producer,
        observed_at=observed_at or (NOW - timedelta(hours=1)),
        scope=scope or ClaimScope(),
        provenance_refs=provenance_refs,
    )


def citation(
    *,
    source_id: str = "study-a",
    content_digest: str = CONTENT_A,
    supports: bool = True,
    claim_text: str = CLAIM_TEXT,
    span: str | None = None,
    locator: str | None = None,
    provenance: bool = True,
    method: str = "direct_quote",
    rationale: str = "",
) -> CitationBinding:
    if span is None:
        span = (
            "Algorithm A decreases measured latency by 10 percent "
            "compared with control."
            if supports
            else "Algorithm A does not decrease measured latency by 10 percent."
        )
    return CitationBinding(
        claim=claim_text,
        source_id=source_id,
        locator=locator or f"doi:{source_id}#result",
        binding_method=method,
        evidence_span=span,
        supports=supports,
        provenance_verified=provenance,
        source_content_sha256=content_digest,
        mapping_rationale=rationale,
    )


def bundle(
    *,
    evidence_value: EvidenceReference | None = None,
    citation_value: CitationBinding | None = None,
    source_value: SourceQualityProfile | None = None,
) -> ClaimEvidenceBundle:
    return ClaimEvidenceBundle(
        evidence=evidence_value or evidence(),
        citation=citation_value or citation(),
        source=source_value or source(),
    )


def second_support(
    *,
    primary: bool = False,
    origin_id: str = "origin-b",
) -> ClaimEvidenceBundle:
    return bundle(
        evidence_value=evidence(
            EVIDENCE_B,
            source_id="study-b",
            origin_id=origin_id,
            content_digest=CONTENT_B,
        ),
        citation_value=citation(
            source_id="study-b",
            content_digest=CONTENT_B,
        ),
        source_value=source(
            "study-b",
            source_class=SourceClass.SECONDARY if not primary else SourceClass.PRIMARY,
            primary=primary,
        ),
    )


def policy(**kwargs) -> ClaimPublicationPolicy:
    defaults = {
        "policy_id": "chat-evidence-v1",
        "min_source_quality": 0.65,
        "min_supporting_origins": 1,
        "min_high_risk_origins": 2,
        "require_primary_for_high_risk": True,
        "require_provenance_refs": True,
        "require_stable_locator": True,
        "require_accountable_publisher": False,
        "requires_current_evidence": False,
        "max_evidence_age_s": None,
        "allow_qualified_independence_shortfall": False,
    }
    defaults.update(kwargs)
    return ClaimPublicationPolicy(**defaults)


def evaluate(
    bundles: tuple[ClaimEvidenceBundle, ...] | list[ClaimEvidenceBundle],
    *,
    claim_value: VerificationClaim | None = None,
    policy_value: ClaimPublicationPolicy | None = None,
):
    return EvidenceCitationPlane().evaluate(
        claim=claim_value or claim(),
        bundles=bundles,
        policy=policy_value or policy(),
        evaluated_at=NOW,
    )


def test_clean_low_risk_claim_is_publishable() -> None:
    receipt = evaluate([bundle()])
    assert receipt.disposition is PublicationDisposition.PUBLISH
    assert receipt.supporting_evidence_ids == (EVIDENCE_A,)
    assert receipt.contradicting_evidence_ids == ()
    assert receipt.production_authority is False


def test_claim_identity_format_variant_is_accepted() -> None:
    item = bundle(
        citation_value=citation(
            claim_text="Algorithm A decreases measured latency by 10%.",
        )
    )
    receipt = evaluate([item])
    assert receipt.disposition is PublicationDisposition.PUBLISH


def test_material_claim_identity_change_is_rejected() -> None:
    item = bundle(
        citation_value=citation(
            claim_text="Algorithm A decreases measured latency by 12 percent.",
            span="Algorithm A decreases measured latency by 12 percent.",
        )
    )
    receipt = evaluate([item])
    assert receipt.disposition is PublicationDisposition.ABSTAIN
    assert "citation_claim_identity_mismatch" in receipt.assessments[0].reasons


def test_content_digest_mismatch_is_rejected() -> None:
    item = bundle(
        citation_value=citation(content_digest=CONTENT_B)
    )
    receipt = evaluate([item])
    assert receipt.disposition is PublicationDisposition.ABSTAIN
    assert "citation_content_digest_mismatch" in receipt.assessments[0].reasons


def test_source_identity_mismatch_is_rejected() -> None:
    item = bundle(source_value=source("study-other"))
    receipt = evaluate([item])
    assert "source_profile_identity_mismatch" in receipt.assessments[0].reasons


def test_citation_source_identity_mismatch_is_rejected() -> None:
    item = bundle(
        citation_value=citation(source_id="study-other")
    )
    receipt = evaluate([item])
    assert "citation_source_identity_mismatch" in receipt.assessments[0].reasons


def test_locator_mismatch_is_rejected() -> None:
    item = bundle(
        citation_value=citation(locator="doi:study-a#wrong")
    )
    receipt = evaluate([item])
    assert "citation_locator_mismatch" in receipt.assessments[0].reasons


def test_quantity_laundering_is_rejected() -> None:
    item = bundle(
        citation_value=citation(
            span="Algorithm A decreases measured latency by 3 percent."
        )
    )
    receipt = evaluate([item])
    assert any(
        reason == "citation_integrity:claim_quantity_not_present_in_evidence_span"
        for reason in receipt.assessments[0].reasons
    )


def test_polarity_laundering_is_rejected() -> None:
    item = bundle(
        citation_value=citation(
            span="Algorithm A does not decrease measured latency by 10 percent."
        )
    )
    receipt = evaluate([item])
    assert "citation_integrity:evidence_polarity_conflict" in (
        receipt.assessments[0].reasons
    )


def test_relation_mismatch_between_reference_and_binding_is_rejected() -> None:
    item = bundle(
        evidence_value=evidence(relation=EvidenceRelation.CONTRADICTS),
        citation_value=citation(supports=True),
    )
    receipt = evaluate([item])
    assert "citation_relation_mismatch" in receipt.assessments[0].reasons


def test_authoritative_contradiction_makes_claim_contested() -> None:
    contradiction = bundle(
        evidence_value=evidence(
            EVIDENCE_B,
            source_id="study-b",
            origin_id="origin-b",
            content_digest=CONTENT_B,
            relation=EvidenceRelation.CONTRADICTS,
        ),
        citation_value=citation(
            source_id="study-b",
            content_digest=CONTENT_B,
            supports=False,
        ),
        source_value=source("study-b"),
    )
    receipt = evaluate([bundle(), contradiction])
    assert receipt.disposition is PublicationDisposition.CONTESTED
    assert receipt.contradicting_evidence_ids == (EVIDENCE_B,)
    assert "authoritative_contradiction_present" in receipt.reasons


def test_model_produced_evidence_is_non_authoritative() -> None:
    item = bundle(
        evidence_value=evidence(producer=EvidenceProducer.MODEL)
    )
    receipt = evaluate([item])
    assert receipt.disposition is PublicationDisposition.ABSTAIN
    assert "evidence_non_authoritative" in receipt.assessments[0].reasons


def test_generated_source_class_is_non_authoritative() -> None:
    item = bundle(
        source_value=source(
            source_class=SourceClass.GENERATED,
            primary=False,
        )
    )
    receipt = evaluate([item])
    assert receipt.disposition is PublicationDisposition.ABSTAIN
    assert "evidence_non_authoritative" in receipt.assessments[0].reasons


def test_missing_provenance_refs_fail_closed_by_default() -> None:
    item = bundle(
        evidence_value=evidence(provenance_refs=())
    )
    receipt = evaluate([item])
    assert "evidence_provenance_refs_missing" in receipt.assessments[0].reasons


def test_policy_can_allow_empty_provenance_refs_for_legacy_read_only_use() -> None:
    item = bundle(
        evidence_value=evidence(provenance_refs=())
    )
    receipt = evaluate(
        [item],
        policy_value=policy(require_provenance_refs=False),
    )
    assert receipt.disposition is PublicationDisposition.PUBLISH


def test_unverified_source_profile_is_rejected() -> None:
    item = bundle(source_value=source(provenance=False))
    receipt = evaluate([item])
    assert "source_profile_provenance_unverified" in receipt.assessments[0].reasons


def test_unverified_citation_provenance_is_rejected() -> None:
    item = bundle(citation_value=citation(provenance=False))
    receipt = evaluate([item])
    assert "citation_provenance_unverified" in receipt.assessments[0].reasons


def test_unstable_locator_is_rejected_when_policy_requires_it() -> None:
    item = bundle(source_value=source(stable=False))
    receipt = evaluate([item])
    assert "source_locator_not_stable" in receipt.assessments[0].reasons


def test_accountable_publisher_can_be_required() -> None:
    item = bundle(source_value=source(accountable=False))
    receipt = evaluate(
        [item],
        policy_value=policy(require_accountable_publisher=True),
    )
    assert "source_publisher_not_accountable" in receipt.assessments[0].reasons


def test_low_source_quality_is_rejected() -> None:
    item = bundle(source_value=source(quality=0.40))
    receipt = evaluate([item])
    assert "source_quality_below_policy" in receipt.assessments[0].reasons


def test_current_claim_rejects_stale_evidence() -> None:
    item = bundle(
        evidence_value=evidence(observed_at=NOW - timedelta(hours=3))
    )
    receipt = evaluate(
        [item],
        policy_value=policy(
            requires_current_evidence=True,
            max_evidence_age_s=3600,
        ),
    )
    assert "evidence_stale_for_current_claim" in receipt.assessments[0].reasons


def test_current_claim_accepts_fresh_evidence() -> None:
    item = bundle(
        evidence_value=evidence(observed_at=NOW - timedelta(minutes=10))
    )
    receipt = evaluate(
        [item],
        policy_value=policy(
            requires_current_evidence=True,
            max_evidence_age_s=3600,
        ),
    )
    assert receipt.disposition is PublicationDisposition.PUBLISH


def test_future_evidence_fails_closed() -> None:
    item = bundle(
        evidence_value=evidence(observed_at=NOW + timedelta(seconds=1))
    )
    receipt = evaluate([item])
    assert "evidence_observed_in_future" in receipt.assessments[0].reasons


def test_current_evidence_policy_requires_explicit_max_age() -> None:
    with pytest.raises(EvidencePlaneError, match="max_evidence_age_s"):
        policy(
            requires_current_evidence=True,
            max_evidence_age_s=None,
        )


def test_duplicate_evidence_id_cannot_double_count_support() -> None:
    first = bundle()
    duplicate = bundle()
    receipt = evaluate([first, duplicate])
    assert receipt.supporting_evidence_ids == (EVIDENCE_A,)
    assert receipt.rejected_evidence_ids == ()
    assert "duplicate_evidence_id" in receipt.assessments[1].reasons


def test_correlated_sources_do_not_satisfy_independent_origin_requirement() -> None:
    receipt = evaluate(
        [bundle(), second_support(origin_id="origin-a")],
        policy_value=policy(min_supporting_origins=2),
    )
    assert receipt.disposition is PublicationDisposition.ABSTAIN
    assert receipt.supporting_origin_ids == ("origin-a",)
    assert "independent_origin_requirement_not_met" in receipt.reasons


def test_independent_sources_satisfy_origin_requirement() -> None:
    receipt = evaluate(
        [bundle(), second_support()],
        policy_value=policy(min_supporting_origins=2),
    )
    assert receipt.disposition is PublicationDisposition.PUBLISH
    assert receipt.supporting_origin_ids == ("origin-a", "origin-b")


def test_independence_shortfall_can_publish_only_with_qualification() -> None:
    receipt = evaluate(
        [bundle()],
        policy_value=policy(
            min_supporting_origins=2,
            allow_qualified_independence_shortfall=True,
        ),
    )
    assert receipt.disposition is PublicationDisposition.PUBLISH_WITH_QUALIFICATION
    assert "independent_origin_requirement_not_met" in receipt.reasons


def test_high_risk_claim_requires_primary_support() -> None:
    low = bundle(
        source_value=source(
            source_class=SourceClass.SECONDARY,
            primary=False,
        )
    )
    other = second_support(primary=False)
    receipt = evaluate(
        [low, other],
        claim_value=claim(risk=VerificationRisk.HIGH),
    )
    assert receipt.disposition is PublicationDisposition.ABSTAIN
    assert "high_risk_claim_requires_primary_source" in receipt.reasons


def test_high_risk_claim_requires_two_independent_origins_by_default() -> None:
    receipt = evaluate(
        [bundle()],
        claim_value=claim(risk=VerificationRisk.HIGH),
    )
    assert receipt.disposition is PublicationDisposition.ABSTAIN
    assert "independent_origin_requirement_not_met" in receipt.reasons


def test_high_risk_claim_with_primary_and_independent_support_publishes() -> None:
    receipt = evaluate(
        [bundle(), second_support()],
        claim_value=claim(risk=VerificationRisk.HIGH),
    )
    assert receipt.disposition is PublicationDisposition.PUBLISH


def test_context_only_evidence_never_becomes_support() -> None:
    item = bundle(
        evidence_value=evidence(relation=EvidenceRelation.CONTEXT_ONLY)
    )
    receipt = evaluate([item])
    assert receipt.disposition is PublicationDisposition.ABSTAIN
    assert receipt.context_evidence_ids == (EVIDENCE_A,)
    assert receipt.supporting_evidence_ids == ()


def test_claim_tenant_mismatch_is_rejected() -> None:
    item = bundle(
        evidence_value=evidence(tenant_id="tenant-b")
    )
    receipt = evaluate([item])
    assert "tenant_mismatch" in receipt.assessments[0].reasons


def test_claim_id_mismatch_is_rejected() -> None:
    item = bundle(
        evidence_value=evidence(
            claim_id="55555555-5555-4555-8555-555555555555"
        )
    )
    receipt = evaluate([item])
    assert "claim_id_mismatch" in receipt.assessments[0].reasons


def test_temporal_scope_mismatch_is_rejected() -> None:
    claim_scope = ClaimScope(valid_from=NOW - timedelta(hours=1))
    evidence_scope = ClaimScope(valid_to=NOW - timedelta(days=1))
    item = bundle(
        evidence_value=evidence(scope=evidence_scope)
    )
    receipt = evaluate(
        [item],
        claim_value=claim(scope=claim_scope),
    )
    assert "temporal_scope_stale" in receipt.assessments[0].reasons


def test_jurisdiction_scope_mismatch_is_rejected() -> None:
    item = bundle(
        evidence_value=evidence(
            scope=ClaimScope(jurisdiction="US")
        )
    )
    receipt = evaluate(
        [item],
        claim_value=claim(scope=ClaimScope(jurisdiction="NO")),
    )
    assert "jurisdiction_scope_mismatch" in receipt.assessments[0].reasons


def test_structured_evidence_requires_mapping_rationale() -> None:
    item = bundle(
        citation_value=citation(
            method="table",
            rationale="",
        )
    )
    receipt = evaluate([item])
    assert (
        "citation_integrity:structured_evidence_mapping_rationale_missing"
        in receipt.assessments[0].reasons
    )


def test_structured_evidence_with_rationale_can_publish() -> None:
    item = bundle(
        citation_value=citation(
            method="table",
            rationale="Table 4 reports the exact latency delta for Algorithm A.",
        )
    )
    receipt = evaluate([item])
    assert receipt.disposition is PublicationDisposition.PUBLISH


def test_policy_digest_changes_when_quality_floor_changes() -> None:
    assert policy(min_source_quality=0.65).digest != policy(
        min_source_quality=0.80
    ).digest


def test_receipt_is_deterministic_for_identical_evidence() -> None:
    plane = EvidenceCitationPlane()
    first = plane.evaluate(
        claim=claim(),
        bundles=(bundle(),),
        policy=policy(),
        evaluated_at=NOW,
    )
    second = plane.evaluate(
        claim=claim(),
        bundles=(bundle(),),
        policy=policy(),
        evaluated_at=NOW,
    )
    assert first.digest == second.digest


def test_receipt_is_non_executing_authority() -> None:
    receipt = evaluate([bundle()])
    assert receipt.authority_scope == "evidence-publication-eligibility-only"
    assert receipt.production_authority is False


def test_source_class_primary_requires_primary_flag() -> None:
    with pytest.raises(EvidencePlaneError, match="primary_source=true"):
        source(
            source_class=SourceClass.PRIMARY,
            primary=False,
        )


def test_generated_source_cannot_claim_primary_status() -> None:
    with pytest.raises(EvidencePlaneError, match="generated source"):
        source(
            source_class=SourceClass.GENERATED,
            primary=True,
        )


def test_claim_identity_canonicalization_stays_strict_on_quantity() -> None:
    engine = ClaimIdentityEngine()
    assert engine.compare(
        "Algorithm A decreases measured latency by 10 percent.",
        "Algorithm A decreases measured latency by 10%.",
    ).identity_equal
    assert not engine.compare(
        "Algorithm A decreases measured latency by 10 percent.",
        "Algorithm A decreases measured latency by 11 percent.",
    ).identity_equal


def test_empty_bundle_set_abstains() -> None:
    receipt = evaluate([])
    assert receipt.disposition is PublicationDisposition.ABSTAIN
    assert receipt.reasons == ("no_authoritative_support",)
