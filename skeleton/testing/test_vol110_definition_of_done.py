from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from skeleton.contracts.definition_of_done import (
    ChangeImpact,
    ChangeImpactProfile,
    CompletionEvidence,
    CompletionSignoff,
    DefinitionOfDone,
    DefinitionOfDoneError,
    DefinitionOfDoneEvaluator,
    DoDRequirement,
    EvidenceKind,
    RequirementStatus,
    completion_evidence_from_promotion_receipt,
    default_definition_of_done,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.maturity_reconciliation import MaturityState
from skeleton.contracts.promotion_evidence import PromotionEvidenceReceipt

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc)
SUBJECT = "a" * 64
ARTIFACT = "b" * 64


def profile(
    impacts: tuple[ChangeImpact, ...] = (ChangeImpact.LOGIC,),
    *,
    owner_id: str = "team.owner",
    builder_id: str = "builder.agent",
) -> ChangeImpactProfile:
    return ChangeImpactProfile(
        subject_id="change.vol110",
        subject_digest=SUBJECT,
        owner_id=owner_id,
        builder_id=builder_id,
        impacts=impacts,
    )


def evidence(
    requirement: DoDRequirement,
    *,
    evidence_id: str | None = None,
    subject_digest: str = SUBJECT,
    observed_at: datetime = NOW - timedelta(minutes=5),
    passed: bool = True,
    producer_id: str = "builder.agent",
    verifier_id: str = "verifier.agent",
    kind: EvidenceKind | None = None,
) -> CompletionEvidence:
    return CompletionEvidence(
        evidence_id=evidence_id or f"ev.{requirement.requirement_id}",
        requirement_id=requirement.requirement_id,
        evidence_kind=kind or requirement.evidence_kind,
        subject_digest=subject_digest,
        artifact_digest=ARTIFACT,
        producer_id=producer_id,
        verifier_id=verifier_id,
        observed_at=observed_at,
        passed=passed,
    )


def active(
    policy: DefinitionOfDone,
    p: ChangeImpactProfile,
    maturity: MaturityState,
) -> tuple[DoDRequirement, ...]:
    return policy.active_requirements(profile=p, target_maturity=maturity)


def evidence_for_active(
    policy: DefinitionOfDone,
    p: ChangeImpactProfile,
    maturity: MaturityState,
) -> tuple[CompletionEvidence, ...]:
    items = []
    for req in active(policy, p, maturity):
        producer = p.owner_id if req.evidence_kind is EvidenceKind.OWNERSHIP else p.builder_id
        verifier = "independent.verifier" if req.independent else "routine.verifier"
        items.append(
            evidence(
                req,
                producer_id=producer,
                verifier_id=verifier,
            )
        )
    return tuple(items)


def evaluate_without_signoff(
    policy: DefinitionOfDone,
    p: ChangeImpactProfile,
    maturity: MaturityState,
    items: tuple[CompletionEvidence, ...],
):
    return DefinitionOfDoneEvaluator().evaluate(
        policy=policy,
        profile=p,
        target_maturity=maturity,
        evidence=items,
        signoff=None,
        at=NOW,
    )


def valid_signoff(
    policy: DefinitionOfDone,
    p: ChangeImpactProfile,
    maturity: MaturityState,
    items: tuple[CompletionEvidence, ...],
    *,
    signer_id: str = "completion.reviewer",
    observed_at: datetime = NOW,
    approved: bool = True,
) -> CompletionSignoff:
    provisional = evaluate_without_signoff(policy, p, maturity, items)
    return CompletionSignoff(
        signoff_id="signoff.vol110",
        subject_digest=p.subject_digest,
        policy_digest=policy.digest,
        target_maturity=maturity,
        evidence_set_digest=provisional.evidence_set_digest,
        signer_id=signer_id,
        observed_at=observed_at,
        approved=approved,
    )


def evaluate(
    policy: DefinitionOfDone,
    p: ChangeImpactProfile,
    maturity: MaturityState,
    items: tuple[CompletionEvidence, ...],
    signoff: CompletionSignoff | None,
):
    return DefinitionOfDoneEvaluator().evaluate(
        policy=policy,
        profile=p,
        target_maturity=maturity,
        evidence=items,
        signoff=signoff,
        at=NOW,
    )


def test_profile_canonicalizes_impact_order() -> None:
    first = profile((ChangeImpact.SECURITY, ChangeImpact.LOGIC))
    second = profile((ChangeImpact.LOGIC, ChangeImpact.SECURITY))

    assert first == second
    assert first.digest == second.digest
    assert first.impacts == (ChangeImpact.LOGIC, ChangeImpact.SECURITY)


def test_profile_rejects_duplicate_and_untyped_impacts() -> None:
    with pytest.raises(DefinitionOfDoneError, match="duplicate"):
        profile((ChangeImpact.LOGIC, ChangeImpact.LOGIC))

    with pytest.raises(DefinitionOfDoneError, match="ChangeImpact"):
        ChangeImpactProfile(
            "change.vol110",
            SUBJECT,
            "team.owner",
            "builder.agent",
            ("logic",),  # type: ignore[arg-type]
        )


def test_requirement_must_be_always_or_impact_triggered() -> None:
    with pytest.raises(DefinitionOfDoneError, match="always-required"):
        DoDRequirement(
            "dod.invalid",
            EvidenceKind.TEST,
            "Invalid requirement.",
            MaturityState.IMPLEMENTED,
        )


def test_policy_identity_is_order_independent() -> None:
    first = default_definition_of_done()
    second = DefinitionOfDone(
        policy_id=first.policy_id,
        version=first.version,
        requirements=tuple(reversed(first.requirements)),
        independent_signoff_required=first.independent_signoff_required,
        signoff_max_age_seconds=first.signoff_max_age_seconds,
    )

    assert first == second
    assert first.digest == second.digest


def test_duplicate_requirement_identity_is_rejected() -> None:
    req = DoDRequirement(
        "dod.same",
        EvidenceKind.TEST,
        "Tests pass.",
        MaturityState.IMPLEMENTED,
        always_required=True,
    )
    with pytest.raises(DefinitionOfDoneError, match="duplicate"):
        DefinitionOfDone("policy.test", 1, (req, req))


def test_dod_rejects_maturity_below_implemented() -> None:
    with pytest.raises(DefinitionOfDoneError, match="implemented maturity"):
        default_definition_of_done().active_requirements(
            profile=profile(),
            target_maturity=MaturityState.SCAFFOLDED,
        )


def test_implemented_logic_requires_base_and_failure_evidence() -> None:
    policy = default_definition_of_done()
    ids = {
        item.requirement_id
        for item in active(policy, profile(), MaturityState.IMPLEMENTED)
    }

    assert ids == {
        "dod.implementation",
        "dod.tests",
        "dod.ownership",
        "dod.failure_behavior",
    }


def test_integrated_persistence_requires_recovery_rollback_and_observability() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.PERSISTENCE,))
    ids = {
        item.requirement_id
        for item in active(policy, p, MaturityState.INTEGRATED)
    }

    assert {
        "dod.implementation",
        "dod.tests",
        "dod.ownership",
        "dod.failure_behavior",
        "dod.observability",
        "dod.rollback",
        "dod.recovery",
    } == ids


def test_integrated_external_effect_requires_compensation_evidence() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.EXTERNAL_EFFECT,))
    ids = {
        item.requirement_id
        for item in active(policy, p, MaturityState.INTEGRATED)
    }

    assert "dod.rollback" in ids
    assert "dod.recovery" in ids
    assert "dod.observability" in ids


def test_integrated_schema_requires_migration_and_rollback() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.SCHEMA,))
    ids = {
        item.requirement_id
        for item in active(policy, p, MaturityState.INTEGRATED)
    }

    assert "dod.migration" in ids
    assert "dod.rollback" in ids


def test_verified_security_requires_independent_security_and_verification() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.SECURITY,))
    by_id = {
        item.requirement_id: item
        for item in active(policy, p, MaturityState.VERIFIED)
    }

    assert by_id["dod.security_review"].independent
    assert by_id["dod.independent_verification"].independent


def test_exact_subject_mismatch_cannot_satisfy_requirement() -> None:
    policy = default_definition_of_done()
    p = profile()
    req = active(policy, p, MaturityState.IMPLEMENTED)[0]
    wrong = evidence(req, subject_digest="c" * 64)

    result = evaluate_without_signoff(
        policy,
        p,
        MaturityState.IMPLEMENTED,
        (wrong,),
    )
    target = next(
        item for item in result.requirements
        if item.requirement_id == req.requirement_id
    )
    assert target.status is RequirementStatus.MISSING


def test_wrong_evidence_kind_cannot_satisfy_requirement() -> None:
    policy = default_definition_of_done()
    p = profile()
    req = next(
        item for item in active(policy, p, MaturityState.IMPLEMENTED)
        if item.requirement_id == "dod.tests"
    )
    wrong = evidence(req, kind=EvidenceKind.IMPLEMENTATION)

    result = evaluate_without_signoff(
        policy,
        p,
        MaturityState.IMPLEMENTED,
        (wrong,),
    )
    target = next(
        item for item in result.requirements
        if item.requirement_id == "dod.tests"
    )
    assert target.status is RequirementStatus.MISSING


def test_failed_latest_evidence_fails_requirement() -> None:
    policy = default_definition_of_done()
    p = profile()
    req = next(
        item for item in active(policy, p, MaturityState.IMPLEMENTED)
        if item.requirement_id == "dod.tests"
    )

    result = evaluate_without_signoff(
        policy,
        p,
        MaturityState.IMPLEMENTED,
        (evidence(req, passed=False),),
    )
    target = next(
        item for item in result.requirements
        if item.requirement_id == "dod.tests"
    )
    assert target.status is RequirementStatus.FAILED


def test_stale_latest_evidence_fails_requirement() -> None:
    req = DoDRequirement(
        "dod.short",
        EvidenceKind.TEST,
        "Fresh test.",
        MaturityState.IMPLEMENTED,
        always_required=True,
        max_age_seconds=60,
    )
    policy = DefinitionOfDone("policy.short", 1, (req,))
    p = profile()

    result = evaluate_without_signoff(
        policy,
        p,
        MaturityState.IMPLEMENTED,
        (evidence(req, observed_at=NOW - timedelta(seconds=61)),),
    )
    assert result.requirements[0].status is RequirementStatus.STALE


def test_ownership_evidence_must_come_from_declared_owner() -> None:
    policy = default_definition_of_done()
    p = profile()
    req = next(
        item for item in active(policy, p, MaturityState.IMPLEMENTED)
        if item.evidence_kind is EvidenceKind.OWNERSHIP
    )

    result = evaluate_without_signoff(
        policy,
        p,
        MaturityState.IMPLEMENTED,
        (evidence(req, producer_id="other.owner"),),
    )
    target = next(
        item for item in result.requirements
        if item.requirement_id == req.requirement_id
    )
    assert target.status is RequirementStatus.OWNER_MISMATCH


def test_independent_requirement_rejects_owner_as_verifier() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.SECURITY,))
    req = next(
        item for item in active(policy, p, MaturityState.VERIFIED)
        if item.requirement_id == "dod.security_review"
    )

    result = evaluate_without_signoff(
        policy,
        p,
        MaturityState.VERIFIED,
        (
            evidence(
                req,
                producer_id="security.reviewer",
                verifier_id=p.owner_id,
            ),
        ),
    )
    target = next(
        item for item in result.requirements
        if item.requirement_id == req.requirement_id
    )
    assert target.status is RequirementStatus.INDEPENDENCE_VIOLATION
    assert not result.eligible


def test_independent_requirement_rejects_builder_as_verifier() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.SECURITY,))
    req = next(
        item for item in active(policy, p, MaturityState.VERIFIED)
        if item.requirement_id == "dod.security_review"
    )

    result = evaluate_without_signoff(
        policy,
        p,
        MaturityState.VERIFIED,
        (
            evidence(
                req,
                producer_id="security.reviewer",
                verifier_id=p.builder_id,
            ),
        ),
    )
    target = next(
        item for item in result.requirements
        if item.requirement_id == req.requirement_id
    )
    assert target.status is RequirementStatus.INDEPENDENCE_VIOLATION


def test_duplicate_evidence_identity_is_rejected() -> None:
    policy = default_definition_of_done()
    p = profile()
    req = active(policy, p, MaturityState.IMPLEMENTED)[0]
    item = evidence(req, evidence_id="ev.duplicate")

    with pytest.raises(DefinitionOfDoneError, match="duplicate"):
        evaluate_without_signoff(
            policy,
            p,
            MaturityState.IMPLEMENTED,
            (item, item),
        )


def test_unknown_requirement_evidence_is_rejected() -> None:
    policy = default_definition_of_done()
    p = profile()
    item = CompletionEvidence(
        "ev.unknown",
        "dod.unknown",
        EvidenceKind.TEST,
        SUBJECT,
        ARTIFACT,
        "builder.agent",
        "verifier.agent",
        NOW,
        True,
    )

    with pytest.raises(DefinitionOfDoneError, match="unknown"):
        evaluate_without_signoff(
            policy,
            p,
            MaturityState.IMPLEMENTED,
            (item,),
        )


def test_missing_independent_signoff_blocks_completion() -> None:
    policy = default_definition_of_done()
    p = profile()
    items = evidence_for_active(policy, p, MaturityState.IMPLEMENTED)

    result = evaluate_without_signoff(
        policy,
        p,
        MaturityState.IMPLEMENTED,
        items,
    )

    assert not result.eligible
    assert "independent_signoff:missing" in result.blockers


def test_self_signoff_by_builder_or_owner_is_rejected() -> None:
    policy = default_definition_of_done()
    p = profile()
    items = evidence_for_active(policy, p, MaturityState.IMPLEMENTED)

    for signer in (p.builder_id, p.owner_id):
        signoff = valid_signoff(
            policy,
            p,
            MaturityState.IMPLEMENTED,
            items,
            signer_id=signer,
        )
        result = evaluate(
            policy,
            p,
            MaturityState.IMPLEMENTED,
            items,
            signoff,
        )
        assert "independent_signoff:not_independent" in result.blockers
        assert not result.eligible


def test_signoff_binds_exact_subject_policy_maturity_and_evidence_set() -> None:
    policy = default_definition_of_done()
    p = profile()
    items = evidence_for_active(policy, p, MaturityState.IMPLEMENTED)
    base = valid_signoff(policy, p, MaturityState.IMPLEMENTED, items)

    variants = (
        CompletionSignoff(
            "signoff.subject",
            "c" * 64,
            base.policy_digest,
            base.target_maturity,
            base.evidence_set_digest,
            base.signer_id,
            base.observed_at,
            True,
        ),
        CompletionSignoff(
            "signoff.policy",
            base.subject_digest,
            "d" * 64,
            base.target_maturity,
            base.evidence_set_digest,
            base.signer_id,
            base.observed_at,
            True,
        ),
        CompletionSignoff(
            "signoff.maturity",
            base.subject_digest,
            base.policy_digest,
            MaturityState.INTEGRATED,
            base.evidence_set_digest,
            base.signer_id,
            base.observed_at,
            True,
        ),
        CompletionSignoff(
            "signoff.evidence",
            base.subject_digest,
            base.policy_digest,
            base.target_maturity,
            "e" * 64,
            base.signer_id,
            base.observed_at,
            True,
        ),
    )

    expected = (
        "independent_signoff:subject_mismatch",
        "independent_signoff:policy_mismatch",
        "independent_signoff:maturity_mismatch",
        "independent_signoff:evidence_set_mismatch",
    )
    for signoff, blocker in zip(variants, expected, strict=True):
        result = evaluate(
            policy,
            p,
            MaturityState.IMPLEMENTED,
            items,
            signoff,
        )
        assert blocker in result.blockers


def test_rejected_future_and_stale_signoff_fail_closed() -> None:
    req = DoDRequirement(
        "dod.test",
        EvidenceKind.TEST,
        "Test evidence.",
        MaturityState.IMPLEMENTED,
        always_required=True,
    )
    policy = DefinitionOfDone(
        "policy.signoff",
        1,
        (req,),
        signoff_max_age_seconds=60,
    )
    p = profile()
    items = (evidence(req, observed_at=NOW - timedelta(seconds=10)),)

    cases = (
        valid_signoff(
            policy,
            p,
            MaturityState.IMPLEMENTED,
            items,
            approved=False,
        ),
        valid_signoff(
            policy,
            p,
            MaturityState.IMPLEMENTED,
            items,
            observed_at=NOW + timedelta(seconds=1),
        ),
        valid_signoff(
            policy,
            p,
            MaturityState.IMPLEMENTED,
            items,
            observed_at=NOW - timedelta(seconds=61),
        ),
    )
    blockers = (
        "independent_signoff:rejected",
        "independent_signoff:future",
        "independent_signoff:stale",
    )
    for signoff, blocker in zip(cases, blockers, strict=True):
        result = evaluate(
            policy,
            p,
            MaturityState.IMPLEMENTED,
            items,
            signoff,
        )
        assert blocker in result.blockers
        assert not result.eligible


def test_signoff_cannot_predate_evidence_it_claims_to_approve() -> None:
    req = DoDRequirement(
        "dod.test",
        EvidenceKind.TEST,
        "Test evidence.",
        MaturityState.IMPLEMENTED,
        always_required=True,
    )
    policy = DefinitionOfDone("policy.chronology", 1, (req,))
    p = profile()
    items = (evidence(req, observed_at=NOW - timedelta(seconds=5)),)
    signoff = valid_signoff(
        policy,
        p,
        MaturityState.IMPLEMENTED,
        items,
        observed_at=NOW - timedelta(seconds=10),
    )

    result = evaluate(
        policy,
        p,
        MaturityState.IMPLEMENTED,
        items,
        signoff,
    )
    assert "independent_signoff:predates_evidence" in result.blockers


def test_complete_implemented_logic_change_is_eligible() -> None:
    policy = default_definition_of_done()
    p = profile()
    items = evidence_for_active(policy, p, MaturityState.IMPLEMENTED)
    signoff = valid_signoff(policy, p, MaturityState.IMPLEMENTED, items)

    result = evaluate(
        policy,
        p,
        MaturityState.IMPLEMENTED,
        items,
        signoff,
    )

    assert result.eligible
    assert result.blockers == ()
    assert all(
        item.status is RequirementStatus.SATISFIED
        for item in result.requirements
    )
    assert result.digest


def test_complete_integrated_persistence_change_is_eligible() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.PERSISTENCE,))
    items = evidence_for_active(policy, p, MaturityState.INTEGRATED)
    signoff = valid_signoff(policy, p, MaturityState.INTEGRATED, items)

    result = evaluate(
        policy,
        p,
        MaturityState.INTEGRATED,
        items,
        signoff,
    )

    assert result.eligible
    assert {
        item.requirement_id for item in result.requirements
    } >= {"dod.rollback", "dod.recovery", "dod.observability"}


def test_complete_verified_security_change_is_eligible() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.SECURITY,))
    items = evidence_for_active(policy, p, MaturityState.VERIFIED)
    signoff = valid_signoff(policy, p, MaturityState.VERIFIED, items)

    result = evaluate(
        policy,
        p,
        MaturityState.VERIFIED,
        items,
        signoff,
    )

    assert result.eligible
    assert {
        item.requirement_id for item in result.requirements
    } >= {"dod.security_review", "dod.independent_verification"}


def test_evidence_order_does_not_change_completion_identity() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.PERSISTENCE,))
    items = evidence_for_active(policy, p, MaturityState.INTEGRATED)
    signoff = valid_signoff(policy, p, MaturityState.INTEGRATED, items)

    first = evaluate(
        policy,
        p,
        MaturityState.INTEGRATED,
        items,
        signoff,
    )
    second = evaluate(
        policy,
        p,
        MaturityState.INTEGRATED,
        tuple(reversed(items)),
        signoff,
    )

    assert first == second
    assert first.digest == second.digest


def test_boolean_impostors_are_rejected_for_evidence_and_signoff() -> None:
    req = DoDRequirement(
        "dod.test",
        EvidenceKind.TEST,
        "Test.",
        MaturityState.IMPLEMENTED,
        always_required=True,
    )
    with pytest.raises(DefinitionOfDoneError, match="passed"):
        CompletionEvidence(
            "ev.test",
            req.requirement_id,
            req.evidence_kind,
            SUBJECT,
            ARTIFACT,
            "builder.agent",
            "verifier.agent",
            NOW,
            1,  # type: ignore[arg-type]
        )

    with pytest.raises(DefinitionOfDoneError, match="approved"):
        CompletionSignoff(
            "signoff.test",
            SUBJECT,
            "c" * 64,
            MaturityState.IMPLEMENTED,
            "d" * 64,
            "reviewer.agent",
            NOW,
            1,  # type: ignore[arg-type]
        )


def test_canonical_and_ai_dod_runtime_are_byte_identical() -> None:
    assert (
        ROOT / "skeleton/contracts/definition_of_done.py"
    ).read_bytes() == (
        ROOT / "skeleton/ai/runtime/contracts/definition_of_done.py"
    ).read_bytes()


def test_policy_cannot_disable_independent_completion_signoff() -> None:
    req = DoDRequirement(
        "dod.test",
        EvidenceKind.TEST,
        "Test evidence.",
        MaturityState.IMPLEMENTED,
        always_required=True,
    )
    with pytest.raises(DefinitionOfDoneError, match="independent signoff is mandatory"):
        DefinitionOfDone(
            "policy.unsafe",
            1,
            (req,),
            independent_signoff_required=False,
        )


def test_hardened_high_risk_change_requires_risk_review() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.AUTHORITY,))
    ids = {
        item.requirement_id
        for item in active(policy, p, MaturityState.HARDENED)
    }

    assert "dod.risk_review" in ids


def test_production_maturity_requires_promotion_evidence() -> None:
    policy = default_definition_of_done()
    p = profile((ChangeImpact.LOGIC,))
    ids = {
        item.requirement_id
        for item in active(policy, p, MaturityState.PRODUCTION)
    }

    assert "dod.promotion" in ids


def promotion_receipt() -> PromotionEvidenceReceipt:
    return PromotionEvidenceReceipt(
        repository="Apeloff1/Skeleton",
        commit_sha="1" * 40,
        task_id="VOL-110",
        accountability_id="ACC-VOL-110",
        configuration_digest="2" * 64,
        environment_digest="3" * 64,
        verifier_id="independent.verifier",
        verifier_digest="4" * 64,
        test_manifest_digest="5" * 64,
        run_id="run.vol110",
        run_attempt=1,
        observed_at=NOW - timedelta(minutes=2),
        evidence=(
            EvidenceRef(
                source="tests:test_vol110",
                digest="6" * 64,
                category="test",
            ),
        ),
    )


def test_promotion_receipt_helper_binds_exact_subject_and_receipt() -> None:
    receipt = promotion_receipt()
    item = completion_evidence_from_promotion_receipt(
        evidence_id="ev.promotion",
        requirement_id="dod.promotion",
        producer_id="release.builder",
        receipt=receipt,
    )

    assert item.evidence_kind is EvidenceKind.PROMOTION
    assert item.subject_digest == receipt.subject_digest
    assert item.artifact_digest == receipt.receipt_digest
    assert item.verifier_id == receipt.verifier_id
    assert item.observed_at == receipt.observed_at


def test_production_promotion_receipt_can_participate_in_exact_completion() -> None:
    policy = default_definition_of_done()
    receipt = promotion_receipt()
    p = ChangeImpactProfile(
        subject_id="change.vol110.production",
        subject_digest=receipt.subject_digest,
        owner_id="team.owner",
        builder_id="release.builder",
        impacts=(ChangeImpact.LOGIC,),
    )
    requirements = active(policy, p, MaturityState.PRODUCTION)
    items = []
    for req in requirements:
        if req.evidence_kind is EvidenceKind.PROMOTION:
            items.append(
                completion_evidence_from_promotion_receipt(
                    evidence_id="ev.promotion",
                    requirement_id=req.requirement_id,
                    producer_id=p.builder_id,
                    receipt=receipt,
                )
            )
            continue
        producer = p.owner_id if req.evidence_kind is EvidenceKind.OWNERSHIP else p.builder_id
        verifier = "independent.verifier" if req.independent else "routine.verifier"
        items.append(
            CompletionEvidence(
                evidence_id=f"ev.{req.requirement_id}",
                requirement_id=req.requirement_id,
                evidence_kind=req.evidence_kind,
                subject_digest=p.subject_digest,
                artifact_digest=ARTIFACT,
                producer_id=producer,
                verifier_id=verifier,
                observed_at=NOW - timedelta(minutes=5),
                passed=True,
            )
        )

    materialized = tuple(items)
    signoff = valid_signoff(
        policy,
        p,
        MaturityState.PRODUCTION,
        materialized,
        signer_id="completion.reviewer",
    )
    result = evaluate(
        policy,
        p,
        MaturityState.PRODUCTION,
        materialized,
        signoff,
    )

    assert result.eligible
    assert any(
        item.requirement_id == "dod.promotion"
        and item.status is RequirementStatus.SATISFIED
        for item in result.requirements
    )
