import pytest
from skeleton.security.autonomy_escalation import *
def req(ok=True,approver="human"):return AutonomyEscalation("r","agent",2,EscalationEvidence("e",ok,approver))
def test_approval_and_eligibility_both_required():
 with pytest.raises(PermissionError):approve_escalation(req(False),now=1,ttl=5,max_level=2)
 with pytest.raises(PermissionError):approve_escalation(req(True,None),now=1,ttl=5,max_level=2)
def test_grant_expires_and_revokes_cleanly():
 g=approve_escalation(req(),now=10,ttl=5,max_level=2);assert g.active(14) and not g.active(15) and not g.revoke(12).active(12)
def test_policy_level_cannot_be_exceeded():
 with pytest.raises(PermissionError):approve_escalation(req(),now=1,ttl=5,max_level=1)

def test_subject_cannot_self_approve():
 import pytest
 r=AutonomyEscalation("r","alice",1,EscalationEvidence("e",True,"alice"))
 with pytest.raises(PermissionError):approve_escalation(r,now=0,ttl=1,max_level=2)
