from __future__ import annotations

from skeleton.ai.runtime.deferred.deployment_operations_assurance import (
    AdminCapability, decide_admin_operation,
)
from skeleton.ai.runtime.deferred.operations_experience import AdminOperation

A="a"*64

def test_high_impact_admin_operation_requires_two_person_approval()->None:
    op=AdminOperation("op","principal","rotate-root",A,True)
    capability=AdminCapability("cap","rotate-root","critical",2,True)
    allowed=decide_admin_operation(
        op,capability,approver_ids=("reviewer-a","reviewer-b"),
    )
    assert allowed.allowed is True
    assert allowed.mutating_authority is False

    blocked=decide_admin_operation(op,capability,approver_ids=("reviewer-a",))
    assert blocked.allowed is False
    assert blocked.blockers==("insufficient-approvals",)

def test_break_glass_requires_explicit_capability()->None:
    op=AdminOperation("op","principal","restart",A,True)
    capability=AdminCapability("cap","restart","medium",1,False)
    decision=decide_admin_operation(
        op,capability,approver_ids=("reviewer",),break_glass=True,
    )
    assert decision.allowed is False
    assert decision.blockers==("break-glass-not-allowed",)
