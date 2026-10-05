import pytest
from skeleton.ai.autonomy_control_theory import *
def test_signal_is_clamped_by_policy_and_resource_bounds():
 c=AutonomyController(10,0,100);s=bounded_control(c,ControlState(0,10),policy_limit=7,resource_limit=5)
 assert s.requested==100 and s.applied==5 and s.clamped
def test_controller_cannot_expand_declared_bound():
 c=AutonomyController(10,0,3);assert bounded_control(c,ControlState(0,10),policy_limit=99,resource_limit=99).applied==3
def test_oscillation_is_explicit_evidence():
 c=AutonomyController(1,-10,10);s=c.evaluate(ControlState(2,1,previous_error=1));assert s.oscillating
def test_invalid_limits_fail_closed():
 with pytest.raises(ValueError):bounded_control(AutonomyController(1,0,1),ControlState(0,1),policy_limit=-1,resource_limit=1)
def test_bad_controller_bounds_rejected():
 with pytest.raises(ValueError):AutonomyController(1,2,1)
