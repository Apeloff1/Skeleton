"""Long-horizon autonomous-worker acceptance for VOL-105."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class AutonomyAcceptanceError(ValueError):pass
class ControlState(str,Enum): ACTIVE="active"; REVOKED="revoked"; OVERRIDDEN="overridden"
class FailureCampaign(str,Enum): INTERRUPTION="interruption"; STALE_WORK="stale_work"; CONFLICT="conflict"; DEADLINE="deadline"; RESOURCE="resource"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise AutonomyAcceptanceError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise AutonomyAcceptanceError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class AutonomyBudgetEvidence:
 budget_id:str;max_steps:int;max_cost_units:int;max_runtime_ticks:int;used_steps:int;used_cost_units:int;used_runtime_ticks:int
 def __post_init__(self):
  object.__setattr__(self,"budget_id",_id(self.budget_id,"budget_id"))
  vals=(self.max_steps,self.max_cost_units,self.max_runtime_ticks)
  used=(self.used_steps,self.used_cost_units,self.used_runtime_ticks)
  if any(isinstance(v,bool) or not isinstance(v,int) or v<1 for v in vals):raise AutonomyAcceptanceError("budget limits must be positive integers")
  if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in used):raise AutonomyAcceptanceError("budget usage invalid")
 @property
 def within_bounds(self):return self.used_steps<=self.max_steps and self.used_cost_units<=self.max_cost_units and self.used_runtime_ticks<=self.max_runtime_ticks
@dataclass(frozen=True,slots=True)
class AutonomyControlEvidence:
 authority_digest:str;delegated_authority:tuple[str,...];parent_authority:tuple[str,...];state:ControlState;override_evidence_digest:str|None
 def __post_init__(self):
  _sha(self.authority_digest,"authority_digest")
  if not isinstance(self.state,ControlState):raise AutonomyAcceptanceError("state must be ControlState")
  for f in ("delegated_authority","parent_authority"):
   raw=getattr(self,f)
   if not isinstance(raw,tuple) or not raw or len(raw)>256 or any(not isinstance(x,str) or not x.strip() for x in raw):raise AutonomyAcceptanceError(f"{f} must be non-empty bounded tuple")
   object.__setattr__(self,f,tuple(sorted(set(x.strip() for x in raw))))
  if not set(self.delegated_authority)<=set(self.parent_authority):raise AutonomyAcceptanceError("delegated authority exceeds parent")
  if self.state is not ControlState.ACTIVE and self.override_evidence_digest is None:raise AutonomyAcceptanceError("revocation/override requires evidence")
  if self.override_evidence_digest is not None:_sha(self.override_evidence_digest,"override_evidence_digest")
@dataclass(frozen=True,slots=True)
class CheckpointEvidence:
 checkpoint_id:str;objective_digest:str;authority_digest:str;state_digest:str;tick:int;recovery_digest:str
 def __post_init__(self):
  object.__setattr__(self,"checkpoint_id",_id(self.checkpoint_id,"checkpoint_id"));_sha(self.objective_digest,"objective_digest");_sha(self.authority_digest,"authority_digest");_sha(self.state_digest,"state_digest");_sha(self.recovery_digest,"recovery_digest")
  if not isinstance(self.tick,int) or isinstance(self.tick,bool) or self.tick<0:raise AutonomyAcceptanceError("checkpoint tick invalid")
@dataclass(frozen=True,slots=True)
class AutonomousWorkerAcceptance:
 acceptance_id:str;objective_digest:str;budget:AutonomyBudgetEvidence;control:AutonomyControlEvidence;checkpoint:CheckpointEvidence;current_tick:int;deadline_tick:int;max_checkpoint_age:int;failure_evidence:tuple[tuple[FailureCampaign,str],...]
 def __post_init__(self):
  object.__setattr__(self,"acceptance_id",_id(self.acceptance_id,"acceptance_id"));_sha(self.objective_digest,"objective_digest")
  if not isinstance(self.budget,AutonomyBudgetEvidence) or not isinstance(self.control,AutonomyControlEvidence) or not isinstance(self.checkpoint,CheckpointEvidence):raise AutonomyAcceptanceError("acceptance evidence must be typed")
  if any(not isinstance(v,int) or isinstance(v,bool) or v<0 for v in (self.current_tick,self.deadline_tick,self.max_checkpoint_age)):raise AutonomyAcceptanceError("time bounds invalid")
  if not isinstance(self.failure_evidence,tuple) or not self.failure_evidence or len(self.failure_evidence)>256:raise AutonomyAcceptanceError("failure_evidence must be non-empty bounded tuple")
  campaigns=set()
  for campaign,d in self.failure_evidence:
   if not isinstance(campaign,FailureCampaign):raise AutonomyAcceptanceError("failure campaign must be FailureCampaign")
   _sha(d,"failure_evidence");campaigns.add(campaign)
  if campaigns!=set(FailureCampaign):raise AutonomyAcceptanceError("failure campaign matrix incomplete")
  if self.checkpoint.objective_digest!=self.objective_digest or self.checkpoint.authority_digest!=self.control.authority_digest:raise AutonomyAcceptanceError("checkpoint identity mismatch")
 @property
 def eligible(self):
  fresh=0<=self.current_tick-self.checkpoint.tick<=self.max_checkpoint_age
  return self.budget.within_bounds and self.control.state is ControlState.ACTIVE and self.current_tick<=self.deadline_tick and fresh and bool(self.failure_evidence)
 @property
 def digest(self):return _dig({"id":self.acceptance_id,"objective":self.objective_digest,"budget":self.budget.__dict__ if hasattr(self.budget,"__dict__") else [self.budget.budget_id,self.budget.max_steps,self.budget.max_cost_units,self.budget.max_runtime_ticks,self.budget.used_steps,self.budget.used_cost_units,self.budget.used_runtime_ticks],"authority":self.control.authority_digest,"control":self.control.state.value,"checkpoint":[self.checkpoint.checkpoint_id,self.checkpoint.objective_digest,self.checkpoint.authority_digest,self.checkpoint.state_digest,self.checkpoint.tick,self.checkpoint.recovery_digest],"current":self.current_tick,"deadline":self.deadline_tick,"max_age":self.max_checkpoint_age,"failure_evidence":self.failure_evidence})

@dataclass(frozen=True,slots=True)
class AutonomyAcceptanceSignoff:
 acceptance_digest:str;reviewer_id:str;approved:bool
 def __post_init__(self):
  _sha(self.acceptance_digest,"acceptance_digest");object.__setattr__(self,"reviewer_id",_id(self.reviewer_id,"reviewer_id"))
  if not isinstance(self.approved,bool):raise AutonomyAcceptanceError("approved must be bool")
def sign_acceptance(bundle:AutonomousWorkerAcceptance,reviewer_id:str)->AutonomyAcceptanceSignoff:
 if not isinstance(bundle,AutonomousWorkerAcceptance) or not bundle.eligible:raise AutonomyAcceptanceError("ineligible autonomy acceptance")
 return AutonomyAcceptanceSignoff(bundle.digest,reviewer_id,True)
def verify_acceptance(bundle:AutonomousWorkerAcceptance,signoff:AutonomyAcceptanceSignoff)->None:
 if not isinstance(bundle,AutonomousWorkerAcceptance) or not isinstance(signoff,AutonomyAcceptanceSignoff):raise AutonomyAcceptanceError("signoff inputs must be typed")
 if not signoff.approved or signoff.acceptance_digest!=bundle.digest:raise AutonomyAcceptanceError("stale or rejected autonomy signoff")
