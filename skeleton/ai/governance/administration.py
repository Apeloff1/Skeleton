"""Least-privilege administration plane contracts for VOL-234."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class AdministrationPlaneError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise AdministrationPlaneError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise AdministrationPlaneError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class AdminPrincipal:
    principal_id:str; scopes:tuple[str,...]; identity_evidence_digest:str
    def __post_init__(self):
        object.__setattr__(self,"principal_id",_token("principal_id",self.principal_id)); object.__setattr__(self,"identity_evidence_digest",_sha("identity_evidence_digest",self.identity_evidence_digest))
        scopes=tuple(sorted({_token("scope",s) for s in self.scopes}))
        if not scopes: raise AdministrationPlaneError("admin principal scopes required")
        object.__setattr__(self,"scopes",scopes)

@dataclass(frozen=True,slots=True)
class AdminRequest:
    request_id:str; principal_id:str; capability:str; resource_id:str; approval_receipt_digest:str|None=None; break_glass_receipt_digest:str|None=None
    def __post_init__(self):
        for n in ("request_id","principal_id","capability","resource_id"): object.__setattr__(self,n,_token(n,getattr(self,n)))
        for n in ("approval_receipt_digest","break_glass_receipt_digest"):
            if getattr(self,n) is not None: object.__setattr__(self,n,_sha(n,getattr(self,n)))

@dataclass(frozen=True,slots=True)
class AdminDecision:
    request_id:str; allowed:bool; reasons:tuple[str,...]; effective_scope:str|None; approval_used:bool; break_glass_used:bool; audit_receipt_required:bool=True; promotion_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"request_id",_token("request_id",self.request_id))
        if not isinstance(self.allowed,bool): raise AdministrationPlaneError("allowed must be boolean")
        reasons=tuple(sorted({_token("reason",r) for r in self.reasons})); object.__setattr__(self,"reasons",reasons)
        if self.effective_scope is not None: object.__setattr__(self,"effective_scope",_token("effective_scope",self.effective_scope))
        if self.allowed==bool(reasons): raise AdministrationPlaneError("allowed/reasons state is inconsistent")
        if self.allowed and self.effective_scope is None: raise AdministrationPlaneError("allowed decision requires effective scope")
        if not self.allowed and self.effective_scope is not None: raise AdministrationPlaneError("denied decision cannot retain effective scope")
        if self.audit_receipt_required is not True: raise AdministrationPlaneError("admin decision must require audit receipt")
        if self.promotion_authority is not False: raise AdministrationPlaneError("admin decision cannot grant promotion authority")

def authorize_admin(*,principal:AdminPrincipal,request:AdminRequest,approval_required:bool=True,break_glass_capabilities:tuple[str,...]=())->AdminDecision:
    if principal.principal_id!=request.principal_id: raise AdministrationPlaneError("principal/request identity mismatch")
    reasons=[]
    if request.capability not in principal.scopes: reasons.append("missing-capability-scope")
    break_glass=request.capability in set(break_glass_capabilities)
    approval_used=request.approval_receipt_digest is not None
    break_used=request.break_glass_receipt_digest is not None
    if break_glass:
        if not break_used: reasons.append("break-glass-receipt-required")
        if approval_used: reasons.append("break-glass-cannot-reuse-normal-approval")
    elif approval_required and not approval_used:
        reasons.append("approval-receipt-required")
    if break_used and not break_glass: reasons.append("break-glass-not-authorized-for-capability")
    allowed=not reasons
    return AdminDecision(request.request_id,allowed,tuple(reasons),request.capability if allowed else None,approval_used,break_used)
