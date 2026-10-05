"""Safe repair, simulation, deployment and scheduling contracts VOL-283..287."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .contracts import sha256_json

def _t(v:object,n:str)->str:
 if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} must be non-empty text")
 return v.strip()
def _d(v:object,n:str)->str:
 v=_t(v,n)
 if len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ValueError(f"{n} must be lowercase sha256")
 return v

@dataclass(frozen=True,slots=True)
class SafeRepairPlan:
 repair_id:str; affected_state_digest:str; mutation_digest:str; rollback_digest:str; target_invariant:str
 def __post_init__(self):
  object.__setattr__(self,"repair_id",_t(self.repair_id,"repair_id"));object.__setattr__(self,"target_invariant",_t(self.target_invariant,"target_invariant"))
  for n in ("affected_state_digest","mutation_digest","rollback_digest"): object.__setattr__(self,n,_d(getattr(self,n),n))
@dataclass(frozen=True,slots=True)
class RepairCheckpoint: repair_id:str; pre_state_digest:str; mutation_applied:bool
@dataclass(frozen=True,slots=True)
class RepairEvidence:
 repair_id:str; post_state_digest:str; invariant_restored:bool; verification_digest:str
def admit_repair_completion(plan:SafeRepairPlan,checkpoint:RepairCheckpoint,evidence:RepairEvidence)->bool:
 if not all((checkpoint.repair_id,evidence.repair_id,evidence.verification_digest)):return False
 try:_d(checkpoint.pre_state_digest,"pre_state_digest");_d(evidence.post_state_digest,"post_state_digest");_d(evidence.verification_digest,"verification_digest")
 except ValueError:return False
 return checkpoint.repair_id==plan.repair_id==evidence.repair_id and checkpoint.pre_state_digest==plan.affected_state_digest and checkpoint.mutation_applied and evidence.invariant_restored

@dataclass(frozen=True,slots=True)
class TwinObservation:
 component:str; observed_state_digest:str; observed_at:str; uncertainty:float; governed:bool
 def __post_init__(self):
  _t(self.component,"component");_d(self.observed_state_digest,"observed_state_digest");_t(self.observed_at,"observed_at")
  if not 0<=self.uncertainty<=1: raise ValueError("uncertainty must be in [0,1]")
@dataclass(frozen=True,slots=True)
class DigitalTwin:
 twin_id:str; observations:tuple[TwinObservation,...]
 @property
 def authoritative(self)->bool: return False
 @property
 def current(self)->bool: return bool(self.observations) and all(o.governed for o in self.observations)
@dataclass(frozen=True,slots=True)
class TwinScenario: scenario_id:str; twin_id:str; proposed_effects:tuple[str,...]; simulation_only:bool=True
 def __post_init__(self):
  if not self.simulation_only: raise ValueError("digital twin cannot authorize real effects")

@dataclass(frozen=True,slots=True)
class DeploymentConstraint:
 max_blast_radius:int; min_slo:float; available_resources:int
@dataclass(frozen=True,slots=True)
class DeploymentProposal:
 proposal_id:str; compatibility_verified:bool; required_resources:int; estimated_blast_radius:int; expected_slo:float; authorized:bool=False
 def __post_init__(self):
  if self.authorized: raise ValueError("planner output cannot self-authorize deployment")
@dataclass(frozen=True,slots=True)
class DeploymentSequence: proposal_id:str; steps:tuple[str,...]; rollback_steps:tuple[str,...]
def plan_deployment(p:DeploymentProposal,c:DeploymentConstraint)->DeploymentSequence|None:
 if not p.compatibility_verified or p.required_resources>c.available_resources or p.estimated_blast_radius>c.max_blast_radius or p.expected_slo<c.min_slo:return None
 return DeploymentSequence(p.proposal_id,("stage","verify","promote"),("stop","rollback","verify"))

@dataclass(frozen=True,slots=True)
class ResourceRequest:
 request_id:str; owner:str; cpu:int; memory:int; priority:int
 def __post_init__(self):
  if self.cpu<=0 or self.memory<=0: raise ValueError("resource request must be positive")
@dataclass(frozen=True,slots=True)
class ResourceLease:
 lease_id:str; request_id:str; owner:str; cpu:int; memory:int; expires_at:str
@dataclass(frozen=True,slots=True)
class PlacementDecision:
 request_id:str; admitted:bool; lease:ResourceLease|None; reason:str
def place(r:ResourceRequest,available_cpu:int,available_memory:int,lease_id:str,expires_at:str)->PlacementDecision:
 if r.cpu>available_cpu or r.memory>available_memory:return PlacementDecision(r.request_id,False,None,"insufficient reserved resources")
 return PlacementDecision(r.request_id,True,ResourceLease(lease_id,r.request_id,r.owner,r.cpu,r.memory,expires_at),"reserved")

@dataclass(frozen=True,slots=True)
class QueueShare: tenant_id:str; weight:int; running:int; waiting:int
@dataclass(frozen=True,slots=True)
class StarvationSignal: tenant_id:str; wait_age:int; starved:bool
@dataclass(frozen=True,slots=True)
class FairnessPolicy: starvation_age:int; max_boost:int
@dataclass(frozen=True,slots=True)
class FairnessDecision: tenant_id:str; boost:int; safety_override:bool
def fairness(policy:FairnessPolicy,share:QueueShare,signal:StarvationSignal,*,security_allowed:bool)->FairnessDecision:
 if not security_allowed:return FairnessDecision(share.tenant_id,0,False)
 boost=min(policy.max_boost,1 if signal.starved and signal.wait_age>=policy.starvation_age else 0)
 return FairnessDecision(share.tenant_id,boost,False)
