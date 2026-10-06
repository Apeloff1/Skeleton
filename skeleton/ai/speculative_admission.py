"""Fail-closed admission and evidence for speculative inference."""
from dataclasses import dataclass
from hashlib import sha256
import json, math
from typing import Iterable
from skeleton.ai.speculative_inference import SpeculativePlan, VerificationStep

def _nn(v,n):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0: raise ValueError(f"{n} must be finite and non-negative")
    return float(v)

@dataclass(frozen=True)
class SpeculativeAdmission:
    quality_floor:float; observed_quality:float; max_extra_cost:float; estimated_extra_cost:float
    available_memory_bytes:int; required_memory_bytes:int
    evaluation_evidence_id:str; budget_evidence_id:str; resource_evidence_id:str
    def __post_init__(self):
        if _nn(self.quality_floor,"quality_floor")>1 or _nn(self.observed_quality,"observed_quality")>1: raise ValueError("quality must be <= 1")
        _nn(self.max_extra_cost,"max_extra_cost"); _nn(self.estimated_extra_cost,"estimated_extra_cost")
        for n in ("available_memory_bytes","required_memory_bytes"):
            v=getattr(self,n)
            if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be a non-negative integer")
        for n in ("evaluation_evidence_id","budget_evidence_id","resource_evidence_id"):
            if not isinstance(getattr(self,n),str) or not getattr(self,n).strip(): raise ValueError(f"{n} is required")
    @property
    def admitted(self):
        return self.observed_quality>=self.quality_floor and self.estimated_extra_cost<=self.max_extra_cost and self.required_memory_bytes<=self.available_memory_bytes

@dataclass(frozen=True)
class SpeculativeExecutionReceipt:
    receipt_id:str; plan_id:str; admitted:bool; accepted_tokens:int; rejected_tokens:int; fallback_required:bool
    evaluation_evidence_id:str; budget_evidence_id:str; resource_evidence_id:str

def _digest(prefix,payload):
    return prefix+sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def plan_identity(plan):
    return _digest("spec-plan-sha256:",{"draft_model":plan.draft_model,"target_model":plan.target_model,"max_tokens":plan.max_tokens,"fallback":plan.fallback})

def authorize_speculation(plan, admission):
    if not admission.admitted: raise PermissionError("speculative inference admission denied")
    return _digest("spec-auth-sha256:",{"plan_id":plan_identity(plan),"quality":[admission.quality_floor,admission.observed_quality],"cost":[admission.max_extra_cost,admission.estimated_extra_cost],"memory":[admission.available_memory_bytes,admission.required_memory_bytes],"evidence":[admission.evaluation_evidence_id,admission.budget_evidence_id,admission.resource_evidence_id]})

def execution_receipt(plan,admission,authorization_id,steps:Iterable[VerificationStep]):
    if authorization_id!=authorize_speculation(plan,admission): raise PermissionError("speculative authorization identity mismatch")
    steps=tuple(steps)
    if len(steps)>plan.max_tokens: raise ValueError("verification exceeds authorized token bound")
    rejected=sum(not s.accepted for s in steps)
    if rejected>1 or (rejected and steps[-1].accepted): raise ValueError("verification trace is not terminal at rejection")
    accepted=sum(s.accepted for s in steps); fallback=plan.fallback and rejected>0
    rid=_digest("spec-receipt-sha256:",{"authorization_id":authorization_id,"plan_id":plan_identity(plan),"accepted_tokens":accepted,"rejected_tokens":rejected,"fallback_required":fallback,"evidence":[admission.evaluation_evidence_id,admission.budget_evidence_id,admission.resource_evidence_id]})
    return SpeculativeExecutionReceipt(rid,plan_identity(plan),True,accepted,rejected,fallback,admission.evaluation_evidence_id,admission.budget_evidence_id,admission.resource_evidence_id)


@dataclass(frozen=True)
class ResourceLease:
    lease_id:str
    generation:int
    issued_at_ns:int
    expires_at_ns:int
    resource_fingerprint:str
    def __post_init__(self):
        if not self.lease_id.strip() or not self.resource_fingerprint.strip(): raise ValueError("lease identity is required")
        for n in ("generation","issued_at_ns","expires_at_ns"):
            v=getattr(self,n)
            if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be a non-negative integer")
        if self.expires_at_ns<=self.issued_at_ns: raise ValueError("lease expiry must follow issue time")

@dataclass(frozen=True)
class SpeculativeAuthorization:
    authorization_id:str
    plan_id:str
    lease_id:str
    lease_generation:int
    expires_at_ns:int
    resource_fingerprint:str

def issue_authorization(plan,admission,lease,now_ns):
    if isinstance(now_ns,bool) or not isinstance(now_ns,int) or now_ns<0: raise ValueError("now_ns must be a non-negative integer")
    if now_ns<lease.issued_at_ns or now_ns>=lease.expires_at_ns: raise PermissionError("resource lease is not live")
    if admission.resource_evidence_id!=lease.lease_id: raise PermissionError("resource evidence does not identify lease")
    base=authorize_speculation(plan,admission)
    aid=_digest("spec-live-auth-sha256:",{"base_authorization_id":base,"lease_id":lease.lease_id,"lease_generation":lease.generation,"expires_at_ns":lease.expires_at_ns,"resource_fingerprint":lease.resource_fingerprint})
    return SpeculativeAuthorization(aid,plan_identity(plan),lease.lease_id,lease.generation,lease.expires_at_ns,lease.resource_fingerprint)

def validate_live_authorization(plan,admission,authorization,lease,now_ns):
    expected=issue_authorization(plan,admission,lease,now_ns)
    if authorization!=expected: raise PermissionError("stale or substituted speculative authorization")
    return True

class AuthorizationLedger:
    """Process-local single-use fence; durable stores can implement the same consume contract."""
    def __init__(self): self._consumed=set()
    def consume(self,authorization):
        aid=authorization.authorization_id
        if aid in self._consumed: raise PermissionError("speculative authorization already consumed")
        self._consumed.add(aid)
        return aid
