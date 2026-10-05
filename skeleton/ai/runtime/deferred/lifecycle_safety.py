"""Lifecycle safety contracts for VOL-260..262."""
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

class MigrationMode(str,Enum): IDEMPOTENT="idempotent"; ATOMIC="atomic"
class MigrationState(str,Enum): PREPARED="prepared"; RUNNING="running"; COMPLETE="complete"; ROLLED_BACK="rolled_back"
@dataclass(frozen=True,slots=True)
class MigrationStep:
 step_id:str; operation_digest:str; idempotency_key:str|None; rollback_operation_digest:str|None
 def __post_init__(self):
  object.__setattr__(self,"step_id",_t(self.step_id,"step_id")); object.__setattr__(self,"operation_digest",_d(self.operation_digest,"operation_digest"))
  if self.idempotency_key is not None: object.__setattr__(self,"idempotency_key",_t(self.idempotency_key,"idempotency_key"))
  if self.rollback_operation_digest is not None: object.__setattr__(self,"rollback_operation_digest",_d(self.rollback_operation_digest,"rollback_operation_digest"))
@dataclass(frozen=True,slots=True)
class MigrationPlan:
 migration_id:str; from_version:str; to_version:str; mode:MigrationMode; mixed_version_supported:bool; steps:tuple[MigrationStep,...]
 def __post_init__(self):
  for n in ("migration_id","from_version","to_version"): object.__setattr__(self,n,_t(getattr(self,n),n))
  if self.from_version==self.to_version or not self.steps: raise ValueError("migration requires distinct versions and steps")
  if len({s.step_id for s in self.steps})!=len(self.steps): raise ValueError("migration step ids must be unique")
  if self.mode is MigrationMode.IDEMPOTENT and any(not s.idempotency_key for s in self.steps): raise ValueError("idempotent migration requires per-step idempotency keys")
@dataclass(frozen=True,slots=True)
class MigrationReceipt:
 migration_id:str; plan_identity:str; state:MigrationState; completed_steps:tuple[str,...]; checkpoint:int
class MigrationEngine:
 def __init__(self,plan:MigrationPlan):
  self.plan=plan; self.completed:list[str]=[]; self.state=MigrationState.PREPARED
  self.identity=sha256_json({"id":plan.migration_id,"from":plan.from_version,"to":plan.to_version,"mode":plan.mode.value,"mixed":plan.mixed_version_supported,"steps":[(s.step_id,s.operation_digest,s.idempotency_key,s.rollback_operation_digest) for s in plan.steps]})
 def apply_next(self)->MigrationReceipt:
  if self.state in (MigrationState.COMPLETE,MigrationState.ROLLED_BACK): raise RuntimeError("migration terminal")
  self.state=MigrationState.RUNNING
  if len(self.completed)<len(self.plan.steps): self.completed.append(self.plan.steps[len(self.completed)].step_id)
  if len(self.completed)==len(self.plan.steps): self.state=MigrationState.COMPLETE
  return self.receipt()
 def resume(self,r:MigrationReceipt)->None:
  if r.migration_id!=self.plan.migration_id or r.plan_identity!=self.identity: raise ValueError("checkpoint does not match migration plan")
  expected=tuple(s.step_id for s in self.plan.steps[:r.checkpoint])
  if r.completed_steps!=expected: raise ValueError("checkpoint history is non-prefix or corrupt")
  self.completed=list(expected); self.state=r.state
 def receipt(self)->MigrationReceipt: return MigrationReceipt(self.plan.migration_id,self.identity,self.state,tuple(self.completed),len(self.completed))

@dataclass(frozen=True,slots=True)
class LegacyConsumer:
 consumer_id:str; adapter_id:str; last_seen_revision:str; supported:bool=True
@dataclass(frozen=True,slots=True)
class ParityEvidence:
 adapter_id:str; canonical_digest:str; legacy_digest:str; evidence_digest:str
 def __post_init__(self):
  for n in ("canonical_digest","legacy_digest","evidence_digest"): object.__setattr__(self,n,_d(getattr(self,n),n))
 @property
 def equivalent(self)->bool: return self.canonical_digest==self.legacy_digest
@dataclass(frozen=True,slots=True)
class CompatibilityAdapter:
 adapter_id:str; canonical_authority:str; legacy_authority_grants:tuple[str,...]=()
 def __post_init__(self):
  object.__setattr__(self,"adapter_id",_t(self.adapter_id,"adapter_id")); object.__setattr__(self,"canonical_authority",_t(self.canonical_authority,"canonical_authority"))
  if self.legacy_authority_grants: raise ValueError("legacy adapter cannot create secondary authority")
def can_remove_adapter(a:CompatibilityAdapter,cs:tuple[LegacyConsumer,...],p:ParityEvidence)->bool:
 return p.adapter_id==a.adapter_id and p.equivalent and not any(c.adapter_id==a.adapter_id and c.supported for c in cs)

class DeprecationState(str,Enum): ACTIVE="active"; DEPRECATED="deprecated"; RETIRED="retired"
@dataclass(frozen=True,slots=True)
class DeprecationWindow: announced_revision:str; removal_revision:str
@dataclass(frozen=True,slots=True)
class Deprecation: feature_id:str; state:DeprecationState; window:DeprecationWindow; policy_revision:str
@dataclass(frozen=True,slots=True)
class RetirementDecision: feature_id:str; allowed:bool; reason:str; consumer_ids:tuple[str,...]
def decide_retirement(d:Deprecation,cs:tuple[LegacyConsumer,...],*,policy_break:bool=False)->RetirementDecision:
 active=tuple(sorted(c.consumer_id for c in cs if c.supported))
 if d.state is not DeprecationState.DEPRECATED: return RetirementDecision(d.feature_id,False,"feature is not deprecated",active)
 if active and not policy_break: return RetirementDecision(d.feature_id,False,"supported consumers remain",active)
 return RetirementDecision(d.feature_id,True,"retirement admitted by policy",active)
