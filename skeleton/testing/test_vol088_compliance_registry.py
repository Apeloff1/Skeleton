from __future__ import annotations

from datetime import date
import hashlib

import pytest

from skeleton.security.compliance import (
    Applicability,
    ComplianceControl,
    ComplianceError,
    ComplianceEvidence,
    ComplianceRegistry,
    ComplianceRequirement,
    ControlKind,
    EvidenceStatus,
    Interpretation,
)

DIGEST = hashlib.sha256(b"artifact").hexdigest()


def requirement(**overrides):
    values = dict(
        requirement_id="REQ.GDPR.32",
        title="Security of processing",
        jurisdiction="EU",
        applicability=Applicability.APPLICABLE,
        owner="privacy-engineering",
        review_date="2027-01-01",
        interpretation=Interpretation.TECHNICAL,
        source_ref="legal-register:gdpr:32",
        rationale="Approved technical mapping; legal interpretation remains external.",
    )
    values.update(overrides)
    return ComplianceRequirement(**values)


def control(**overrides):
    values = dict(
        control_id="CTRL.ENCRYPT.01",
        requirement_id="REQ.GDPR.32",
        kind=ControlKind.SECURITY,
        owner="security-platform",
        implementation_ref="skeleton/security/encryption",
        verifier_id="VERIFY.ENCRYPT.01",
    )
    values.update(overrides)
    return ComplianceControl(**values)


def evidence(**overrides):
    values = dict(
        evidence_id="EVID.ENCRYPT.20261005",
        requirement_id="REQ.GDPR.32",
        control_id="CTRL.ENCRYPT.01",
        verifier_id="VERIFY.ENCRYPT.01",
        observed_at="2026-10-05T12:00:00Z",
        artifact_digest=DIGEST,
        status=EvidenceStatus.SATISFIED,
    )
    values.update(overrides)
    return ComplianceEvidence(**values)


def complete_registry():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement())
    registry.add_control(control())
    registry.add_evidence(evidence())
    return registry


def test_complete_current_mapping_is_satisfied():
    assessment = complete_registry().assess("REQ.GDPR.32", on_date=date(2026, 10, 5))
    assert assessment.decision is EvidenceStatus.SATISFIED
    assert assessment.reasons == ()
    assert len(assessment.control_digests) == 1
    assert len(assessment.evidence_digests) == 1


def test_legal_interpretation_cannot_be_auto_declared_applicable():
    with pytest.raises(ComplianceError, match="cannot be auto-declared applicable"):
        requirement(interpretation=Interpretation.LEGAL_REVIEW)


def test_review_required_legal_item_fails_closed_even_with_evidence():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement(
        applicability=Applicability.REVIEW_REQUIRED,
        interpretation=Interpretation.LEGAL_REVIEW,
    ))
    registry.add_control(control())
    registry.add_evidence(evidence())
    result = registry.assess("REQ.GDPR.32", on_date=date(2026, 10, 5))
    assert result.decision is EvidenceStatus.UNKNOWN
    assert "legal_or_applicability_review_required" in result.reasons


def test_expired_review_fails_closed():
    registry = complete_registry()
    result = registry.assess("REQ.GDPR.32", on_date=date(2027, 1, 2))
    assert result.decision is EvidenceStatus.UNKNOWN
    assert "requirement_review_expired" in result.reasons


def test_missing_control_is_unknown_not_satisfied():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement())
    result = registry.assess("REQ.GDPR.32", on_date=date(2026, 10, 5))
    assert result.decision is EvidenceStatus.UNKNOWN
    assert "no_controls" in result.reasons


def test_missing_evidence_is_unknown():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement())
    registry.add_control(control())
    result = registry.assess("REQ.GDPR.32", on_date=date(2026, 10, 5))
    assert result.decision is EvidenceStatus.UNKNOWN
    assert result.reasons == ("missing_evidence:CTRL.ENCRYPT.01",)


def test_explicit_failed_evidence_is_failed():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement())
    registry.add_control(control())
    registry.add_evidence(evidence(status=EvidenceStatus.FAILED))
    result = registry.assess("REQ.GDPR.32", on_date=date(2026, 10, 5))
    assert result.decision is EvidenceStatus.FAILED


def test_unknown_evidence_is_unknown():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement())
    registry.add_control(control())
    registry.add_evidence(evidence(status=EvidenceStatus.UNKNOWN))
    result = registry.assess("REQ.GDPR.32", on_date=date(2026, 10, 5))
    assert result.decision is EvidenceStatus.UNKNOWN


def test_control_must_reference_existing_requirement():
    registry = ComplianceRegistry()
    with pytest.raises(ComplianceError, match="unknown requirement"):
        registry.add_control(control())


def test_evidence_cannot_cross_requirement_boundary():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement())
    registry.add_requirement(requirement(
        requirement_id="REQ.NIS2.21",
        title="Risk management",
        source_ref="legal-register:nis2:21",
    ))
    registry.add_control(control())
    with pytest.raises(ComplianceError, match="crosses requirement boundary"):
        registry.add_evidence(evidence(requirement_id="REQ.NIS2.21"))


def test_evidence_verifier_must_match_control_owner():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement())
    registry.add_control(control())
    with pytest.raises(ComplianceError, match="verifier does not own"):
        registry.add_evidence(evidence(verifier_id="VERIFY.OTHER.01"))


def test_identity_is_immutable():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement())
    with pytest.raises(ComplianceError, match="identity is immutable"):
        registry.add_requirement(requirement(title="Changed behind stable identity"))


def test_evidence_requires_sha256_and_utc():
    with pytest.raises(ComplianceError, match="lowercase sha256"):
        evidence(artifact_digest="abc")
    with pytest.raises(ComplianceError, match="UTC Z"):
        evidence(observed_at="2026-10-05T12:00:00+02:00")


def test_inventory_digest_is_insertion_order_independent():
    first = ComplianceRegistry()
    first.add_requirement(requirement())
    first.add_control(control())
    first.add_evidence(evidence())

    second = ComplianceRegistry()
    second.add_requirement(requirement())
    second.add_control(control())
    second.add_evidence(evidence())

    assert first.inventory_digest() == second.inventory_digest()


def test_latest_evidence_controls_current_assessment():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement())
    registry.add_control(control())
    registry.add_evidence(evidence(
        evidence_id="EVID.ENCRYPT.20261004",
        observed_at="2026-10-04T12:00:00Z",
        status=EvidenceStatus.FAILED,
    ))
    registry.add_evidence(evidence())
    assert registry.assess("REQ.GDPR.32", on_date=date(2026, 10, 5)).decision is EvidenceStatus.SATISFIED


def test_not_applicable_is_explicit_and_does_not_require_controls():
    registry = ComplianceRegistry()
    registry.add_requirement(requirement(applicability=Applicability.NOT_APPLICABLE))
    result = registry.assess("REQ.GDPR.32", on_date=date(2026, 10, 5))
    assert result.decision is EvidenceStatus.SATISFIED
    assert result.reasons == ("explicitly_not_applicable",)
