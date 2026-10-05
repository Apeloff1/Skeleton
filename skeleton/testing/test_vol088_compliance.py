from datetime import datetime,timedelta,timezone
import pytest
from skeleton.contracts.compliance import *

def setup_registry():
    req=ComplianceRequirement("REQ-1","policy.example","Retain immutable evidence","security.owner")
    ctrl=ComplianceControl("CTRL-1","security.owner",("REQ-1",),3600,"Verify immutable evidence")
    return ComplianceRegistry((req,),(ctrl,)),ctrl

def evidence(ctrl,now,result=EvidenceResult.PASS,**kw):
    values=dict(evidence_id="EV-1",control_id=ctrl.control_id,control_digest=ctrl.digest,owner=ctrl.owner,artifact_digest="a"*64,observed_at=now,result=result); values.update(kw); return ComplianceEvidence(**values)

def test_identity_is_deterministic_and_order_independent():
    a=ComplianceRequirement("REQ-A","policy.a","A statement","owner.a"); b=ComplianceRequirement("REQ-B","policy.b","B statement","owner.b",RequirementDisposition.NOT_APPLICABLE,"out of scope")
    ca=ComplianceControl("CTRL-A","owner.a",("REQ-A",),60,"A control"); cb=ComplianceControl("CTRL-B","owner.b",("REQ-B",),60,"B control")
    assert ComplianceRegistry((a,b),(ca,cb)).digest==ComplianceRegistry((b,a),(cb,ca)).digest

def test_missing_or_mismatched_evidence_fails_closed():
    registry,ctrl=setup_registry(); now=datetime(2026,1,1,tzinfo=timezone.utc)
    assert registry.assess((),at=now).controls[0].status is ControlStatus.EVIDENCE_MISSING
    assert registry.assess((evidence(ctrl,now,control_digest="b"*64),),at=now).controls[0].status is ControlStatus.EVIDENCE_MISSING

def test_stale_and_failed_evidence_never_complies():
    registry,ctrl=setup_registry(); now=datetime(2026,1,1,tzinfo=timezone.utc)
    stale=registry.assess((evidence(ctrl,now-timedelta(seconds=3601)),),at=now); failed=registry.assess((evidence(ctrl,now,EvidenceResult.FAIL),),at=now)
    assert stale.controls[0].status is ControlStatus.EVIDENCE_STALE and not stale.compliant
    assert failed.controls[0].status is ControlStatus.FAILED and not failed.compliant

def test_fresh_pass_and_not_applicable_are_explicit():
    registry,ctrl=setup_registry(); now=datetime(2026,1,1,tzinfo=timezone.utc)
    assert registry.assess((evidence(ctrl,now),),at=now).compliant
    req=ComplianceRequirement("REQ-X","policy.x","Out of scope","owner.x",RequirementDisposition.NOT_APPLICABLE,"disabled")
    c=ComplianceControl("CTRL-X","owner.x",("REQ-X",),60,"Applicability control")
    assert ComplianceRegistry((req,),(c,)).assess((),at=now).controls[0].status is ControlStatus.NOT_APPLICABLE

def test_uncontrolled_required_requirement_is_rejected():
    req=ComplianceRequirement("REQ-1","policy.x","Must be controlled","owner.a"); other=ComplianceRequirement("REQ-2","policy.x","Other","owner.b",RequirementDisposition.NOT_APPLICABLE,"excluded"); c=ComplianceControl("CTRL-2","owner.b",("REQ-2",),60,"Other control")
    with pytest.raises(ComplianceError,match="lacks control"): ComplianceRegistry((req,other),(c,))

def test_future_and_unknown_evidence_fail_closed():
    registry,ctrl=setup_registry(); now=datetime(2026,1,1,tzinfo=timezone.utc)
    assert registry.assess((evidence(ctrl,now+timedelta(seconds=1)),),at=now).controls[0].status is ControlStatus.EVIDENCE_MISSING
    with pytest.raises(ComplianceError,match="unknown control"): registry.assess((evidence(ctrl,now,control_id="CTRL-X"),),at=now)
