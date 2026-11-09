from datetime import datetime, timedelta, timezone

import pytest

from skeleton.contracts.compliance import (
    ComplianceControl,
    ComplianceError,
    ComplianceEvidence,
    ComplianceRegistry,
    ComplianceRequirement,
    ControlKind,
    ControlStatus,
    EnforcementMode,
    EvidenceResult,
    RequirementDisposition,
)

NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)


def requirement(
    requirement_id="REQ-1",
    *,
    disposition=RequirementDisposition.REQUIRED,
    reviewed_at=NOW,
    review_ttl_seconds=86400,
    jurisdiction="NO",
):
    return ComplianceRequirement(
        requirement_id=requirement_id,
        source="policy.example",
        jurisdiction=jurisdiction,
        statement="Retain immutable evidence",
        owner="security.owner",
        legal_reviewer="legal.owner",
        reviewed_at=reviewed_at,
        review_ttl_seconds=review_ttl_seconds,
        disposition=disposition,
        applicability_reason="in scope" if disposition is RequirementDisposition.REQUIRED else "out of scope",
    )


def control(
    requirement_ids=("REQ-1",),
    *,
    mode=EnforcementMode.TECHNICAL,
    kind=ControlKind.SECURITY,
    implementation_ref="skeleton/security/evidence",
    verifier_id="verify.evidence.v1",
):
    return ComplianceControl(
        control_id="CTRL-1",
        owner="security.owner",
        requirement_ids=requirement_ids,
        evidence_ttl_seconds=3600,
        description="Verify immutable evidence",
        kind=kind,
        implementation_ref=implementation_ref,
        verifier_id=verifier_id,
        enforcement_mode=mode,
    )


def evidence(ctrl, *, observed_at=NOW, result=EvidenceResult.PASS, **overrides):
    values = {
        "evidence_id": "EV-1",
        "control_id": ctrl.control_id,
        "control_digest": ctrl.digest,
        "owner": ctrl.owner,
        "verifier_id": ctrl.verifier_id,
        "artifact_digest": "a" * 64,
        "observed_at": observed_at,
        "result": result,
    }
    values.update(overrides)
    return ComplianceEvidence(**values)


def registry(req=None, ctrl=None):
    req = req or requirement()
    ctrl = ctrl or control((req.requirement_id,))
    return ComplianceRegistry((req,), (ctrl,)), ctrl


def test_registry_identity_is_order_independent_and_jurisdiction_bound():
    a = requirement("REQ-A", jurisdiction="NO")
    b = requirement("REQ-B", jurisdiction="EU")
    ca = ComplianceControl(
        "CTRL-A",
        "security.owner",
        ("REQ-A",),
        60,
        "A",
        ControlKind.SECURITY,
        "skeleton/security/a",
        "verify.a.v1",
    )
    cb = ComplianceControl(
        "CTRL-B",
        "security.owner",
        ("REQ-B",),
        60,
        "B",
        ControlKind.RETENTION,
        "skeleton/security/b",
        "verify.b.v1",
    )
    first = ComplianceRegistry((a, b), (ca, cb))
    second = ComplianceRegistry((b, a), (cb, ca))
    assert first.digest == second.digest
    changed = ComplianceRegistry(
        (requirement("REQ-A", jurisdiction="US"), b),
        (ca, cb),
    )
    assert changed.digest != first.digest


def test_required_requirement_without_control_is_rejected():
    req = requirement()
    other = requirement("REQ-2", disposition=RequirementDisposition.NOT_APPLICABLE)
    other_control = control(("REQ-2",))
    with pytest.raises(ComplianceError, match="lacks control"):
        ComplianceRegistry((req, other), (other_control,))


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, ControlStatus.EVIDENCE_MISSING),
        ({"control_digest": "b" * 64}, ControlStatus.EVIDENCE_MISSING),
        ({"owner": "other.owner"}, ControlStatus.EVIDENCE_MISSING),
        (
            {"observed_at": NOW + timedelta(seconds=1)},
            ControlStatus.EVIDENCE_MISSING,
        ),
    ],
)
def test_unbound_or_future_evidence_fails_closed(kwargs, expected):
    reg, ctrl = registry()
    items = () if not kwargs else (evidence(ctrl, **kwargs),)
    assessment = reg.assess(items, at=NOW)
    assert assessment.controls[0].status is expected
    assert not assessment.compliant


def test_stale_and_failed_evidence_never_complies():
    reg, ctrl = registry()
    stale = reg.assess(
        (evidence(ctrl, observed_at=NOW - timedelta(seconds=3601)),),
        at=NOW,
    )
    failed = reg.assess(
        (evidence(ctrl, result=EvidenceResult.FAIL),),
        at=NOW,
    )
    assert stale.controls[0].status is ControlStatus.EVIDENCE_STALE
    assert failed.controls[0].status is ControlStatus.FAILED
    assert not stale.compliant
    assert not failed.compliant


def test_fresh_identity_bound_pass_is_compliant():
    reg, ctrl = registry()
    assessment = reg.assess((evidence(ctrl),), at=NOW)
    assert assessment.controls[0].status is ControlStatus.SATISFIED
    assert assessment.compliant


def test_stale_applicability_review_blocks_even_fresh_passing_evidence():
    req = requirement(
        reviewed_at=NOW - timedelta(days=2),
        review_ttl_seconds=86400,
    )
    reg, ctrl = registry(req=req)
    assessment = reg.assess((evidence(ctrl),), at=NOW)
    assert assessment.controls[0].status is ControlStatus.APPLICABILITY_STALE
    assert assessment.controls[0].evidence_digest is None
    assert not assessment.compliant


def test_future_dated_legal_review_fails_closed():
    req = requirement(reviewed_at=NOW + timedelta(seconds=1))
    reg, ctrl = registry(req=req)
    assessment = reg.assess((), at=NOW)
    assert assessment.controls[0].status is ControlStatus.APPLICABILITY_STALE
    assert not assessment.compliant


def test_review_only_legal_interpretation_cannot_be_auto_satisfied():
    req = requirement()
    ctrl = control(mode=EnforcementMode.REVIEW_ONLY)
    reg = ComplianceRegistry((req,), (ctrl,))
    assessment = reg.assess((evidence(ctrl),), at=NOW)
    assert assessment.controls[0].status is ControlStatus.REVIEW_REQUIRED
    assert assessment.controls[0].evidence_digest is None
    assert not assessment.compliant


def test_reviewed_not_applicable_is_explicit_and_requires_current_review():
    req = requirement(disposition=RequirementDisposition.NOT_APPLICABLE)
    reg, _ = registry(req=req)
    assessment = reg.assess((), at=NOW)
    assert assessment.controls[0].status is ControlStatus.NOT_APPLICABLE
    assert assessment.compliant

    stale = requirement(
        disposition=RequirementDisposition.NOT_APPLICABLE,
        reviewed_at=NOW - timedelta(days=2),
        review_ttl_seconds=86400,
    )
    stale_reg, _ = registry(req=stale)
    stale_assessment = stale_reg.assess((), at=NOW)
    assert stale_assessment.controls[0].status is ControlStatus.APPLICABILITY_STALE
    assert not stale_assessment.compliant


def test_duplicate_evidence_identity_is_rejected():
    reg, ctrl = registry()
    first = evidence(ctrl)
    duplicate = evidence(
        ctrl,
        observed_at=NOW - timedelta(seconds=1),
        result=EvidenceResult.FAIL,
    )
    with pytest.raises(ComplianceError, match="duplicate evidence id"):
        reg.assess((first, duplicate), at=NOW)


def test_unknown_control_evidence_is_rejected():
    reg, ctrl = registry()
    with pytest.raises(ComplianceError, match="unknown control"):
        reg.assess((evidence(ctrl, control_id="CTRL-X"),), at=NOW)


def test_duplicate_ids_and_unknown_requirement_mapping_are_rejected():
    req = requirement()
    ctrl = control()
    with pytest.raises(ComplianceError, match="duplicate requirement"):
        ComplianceRegistry((req, req), (ctrl,))
    bad = control(("REQ-X",))
    with pytest.raises(ComplianceError, match="unknown requirement"):
        ComplianceRegistry((req,), (bad,))


def test_noncanonical_time_precision_and_digest_are_rejected():
    with pytest.raises(ComplianceError, match="whole-second"):
        requirement(reviewed_at=NOW.replace(microsecond=1))
    reg, ctrl = registry()
    del reg
    with pytest.raises(ComplianceError, match="sha256"):
        evidence(ctrl, artifact_digest="A" * 64)


def test_canonical_and_governed_ai_mirror_are_byte_identical():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    canonical = root / "skeleton/contracts/compliance.py"
    mirror = root / "skeleton/ai/runtime/contracts/compliance.py"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_verifier_substitution_cannot_satisfy_control():
    reg, ctrl = registry()
    assessment = reg.assess(
        (evidence(ctrl, verifier_id="verify.other.v1"),),
        at=NOW,
    )
    assert assessment.controls[0].status is ControlStatus.EVIDENCE_MISSING
    assert not assessment.compliant


def test_control_identity_binds_kind_implementation_and_verifier():
    original = control()
    changed_kind = control(kind=ControlKind.RETENTION)
    changed_impl = control(implementation_ref="skeleton/security/other")
    changed_verifier = control(verifier_id="verify.other.v1")

    assert original.digest != changed_kind.digest
    assert original.digest != changed_impl.digest
    assert original.digest != changed_verifier.digest


def test_evidence_digest_binds_verifier_identity():
    _, ctrl = registry()
    original = evidence(ctrl)
    substituted = evidence(ctrl, verifier_id="verify.other.v1")

    assert original.digest != substituted.digest

def test_conflicting_equally_fresh_evidence_fails_closed_regardless_of_order():
    ctrl = control()
    reg, _ = registry(ctrl=ctrl)
    passed = evidence(ctrl, evidence_id="EV-PASS", artifact_digest="a"*64, result=EvidenceResult.PASS)
    failed = evidence(ctrl, evidence_id="EV-FAIL", artifact_digest="b"*64, result=EvidenceResult.FAIL)

    first = reg.assess((passed, failed), at=NOW)
    second = reg.assess((failed, passed), at=NOW)

    assert first.controls[0].status is ControlStatus.FAILED
    assert second.controls[0].status is ControlStatus.FAILED
    assert "cohort contains failure" in first.controls[0].reason
    assert first.compliant is False
    assert second.compliant is False
