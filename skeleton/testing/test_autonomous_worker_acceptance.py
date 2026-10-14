from __future__ import annotations
import hashlib,pytest
from skeleton.eval.autonomy_acceptance import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def budget(**kw):
 v=dict(budget_id="BUDGET.1",max_steps=10,max_cost_units=10,max_runtime_ticks=10,used_steps=5,used_cost_units=5,used_runtime_ticks=5);v.update(kw);return AutonomyBudgetEvidence(**v)
def control(state=ControlState.ACTIVE):return AutonomyControlEvidence(S("auth"),("READ",),("READ","WRITE"),state,None if state is ControlState.ACTIVE else S("override"))
def cp(tick=5,objective=S("objective"),authority=S("auth")):return CheckpointEvidence("CHECKPOINT.1",objective,authority,S("state"),tick,S("recovery"))
def acc(**kw):
 v=dict(acceptance_id="ACCEPT.105",objective_digest=S("objective"),budget=budget(),control=control(),checkpoint=cp(),current_tick=6,deadline_tick=10,max_checkpoint_age=2,failure_evidence=tuple((x,S(x.value)) for x in FailureCampaign));v.update(kw);return AutonomousWorkerAcceptance(**v)
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
 with pytest.raises(AutonomyAcceptanceError,match="checkpoint tick invalid"):CheckpointEvidence("CHECKPOINT.X",S("objective"),S("auth"),S("s"),True,S("r"))
 with pytest.raises(AutonomyAcceptanceError,match="time bounds invalid"):acc(current_tick=True)
def test_authority_and_failure_evidence_are_bounded_tuples():
 with pytest.raises(AutonomyAcceptanceError,match="bounded tuple"):AutonomyControlEvidence(S("a"),["READ"],("READ",),ControlState.ACTIVE,None)
 with pytest.raises(AutonomyAcceptanceError,match="failure_evidence"):acc(failure_evidence=[])

def test_failure_campaign_matrix_must_be_complete():
 partial=((FailureCampaign.INTERRUPTION,S("i")),)
 with pytest.raises(AutonomyAcceptanceError,match="matrix incomplete"):acc(failure_evidence=partial)
def test_checkpoint_cannot_replay_under_different_objective():
 with pytest.raises(AutonomyAcceptanceError,match="checkpoint identity mismatch"):acc(checkpoint=cp(objective=S("other")))
def test_checkpoint_cannot_replay_after_authority_identity_changes():
 changed=AutonomyControlEvidence(S("new-auth"),("READ",),("READ","WRITE"),ControlState.ACTIVE,None)
 with pytest.raises(AutonomyAcceptanceError,match="checkpoint identity mismatch"):acc(control=changed)

def test_signoff_binds_exact_long_horizon_evidence():
 a=acc();s=sign_acceptance(a,"ACTOR.REVIEWER");verify_acceptance(a,s)
 changed=acc(current_tick=7)
 with pytest.raises(AutonomyAcceptanceError,match="stale or rejected"):verify_acceptance(changed,s)
def test_ineligible_worker_cannot_be_signed():
 with pytest.raises(AutonomyAcceptanceError,match="ineligible"):sign_acceptance(acc(control=control(ControlState.REVOKED)),"ACTOR.REVIEWER")

def test_governed_mirror_exports_identical_contract():
 from skeleton.ai.evaluation import autonomy_acceptance as governed
 assert governed.CheckpointEvidence.__annotations__ == CheckpointEvidence.__annotations__
 assert governed.FailureCampaign is not FailureCampaign
 assert tuple(x.value for x in governed.FailureCampaign) == tuple(x.value for x in FailureCampaign)

def test_checkpoint_digest_fields_reject_forgery():
 with pytest.raises(AutonomyAcceptanceError,match="objective_digest must be sha256"):
  CheckpointEvidence("CHECKPOINT.X","forged",S("auth"),S("state"),1,S("recovery"))
 with pytest.raises(AutonomyAcceptanceError,match="authority_digest must be sha256"):
  CheckpointEvidence("CHECKPOINT.X",S("objective"),"forged",S("state"),1,S("recovery"))
