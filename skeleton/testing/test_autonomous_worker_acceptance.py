from __future__ import annotations
import hashlib,pytest
from skeleton.eval.autonomy_acceptance import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def budget(**kw):
 v=dict(budget_id="BUDGET.1",max_steps=10,max_cost_units=10,max_runtime_ticks=10,used_steps=5,used_cost_units=5,used_runtime_ticks=5);v.update(kw);return AutonomyBudgetEvidence(**v)
def control(state=ControlState.ACTIVE):return AutonomyControlEvidence(S("auth"),("READ",),("READ","WRITE"),state,None if state is ControlState.ACTIVE else S("override"))
def cp(tick=5):return CheckpointEvidence("CHECKPOINT.1",S("state"),tick,S("recovery"))
def acc(**kw):
 v=dict(acceptance_id="ACCEPT.105",objective_digest=S("objective"),budget=budget(),control=control(),checkpoint=cp(),current_tick=6,deadline_tick=10,max_checkpoint_age=2,failure_evidence=(S("interruption"),S("resource")));v.update(kw);return AutonomousWorkerAcceptance(**v)
def test_bounded_fresh_worker_is_eligible():assert acc().eligible
def test_budget_exhaustion_blocks_acceptance():assert not acc(budget=budget(used_steps=11)).eligible
def test_deadline_exhaustion_blocks_acceptance():assert not acc(current_tick=11).eligible
def test_stale_checkpoint_blocks_acceptance():assert not acc(current_tick=9).eligible
def test_revoked_authority_blocks_zombie_work():assert not acc(control=control(ControlState.REVOKED)).eligible
def test_missing_failure_campaign_evidence_blocks_acceptance():assert not acc(failure_evidence=()).eligible
def test_delegation_cannot_expand_parent_authority():
 try:AutonomyControlEvidence(S("a"),("ROOT",),("READ",),ControlState.ACTIVE,None);assert False
 except AutonomyAcceptanceError as e:assert "exceeds" in str(e)

def test_control_state_and_time_aliases_fail_closed():
 with pytest.raises(AutonomyAcceptanceError,match="state must be ControlState"):AutonomyControlEvidence(S("a"),("READ",),("READ",),"active",None)
 with pytest.raises(AutonomyAcceptanceError,match="checkpoint tick invalid"):CheckpointEvidence("CHECKPOINT.X",S("s"),True,S("r"))
 with pytest.raises(AutonomyAcceptanceError,match="time bounds invalid"):acc(current_tick=True)
def test_authority_and_failure_evidence_are_bounded_tuples():
 with pytest.raises(AutonomyAcceptanceError,match="bounded tuple"):AutonomyControlEvidence(S("a"),["READ"],("READ",),ControlState.ACTIVE,None)
 with pytest.raises(AutonomyAcceptanceError,match="failure_evidence"):acc(failure_evidence=[])
