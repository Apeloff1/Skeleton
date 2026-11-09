"""Fail-closed external identity federation for VOL-233."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class IdentityFederationError(ValueError): pass

def _token(n:str,v:object,max_length:int=512)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>max_length: raise IdentityFederationError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise IdentityFederationError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str:return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class FederatedPrincipalMapping:
    issuer_id:str; external_subject:str; local_principal_id:str; tenant_id:str; allowed_scopes:tuple[str,...]; mapping_evidence_digest:str
    def __post_init__(self):
        for n in ("issuer_id","external_subject","local_principal_id","tenant_id"): object.__setattr__(self,n,_token(n,getattr(self,n)))
        scopes=tuple(sorted({_token("scope",s) for s in self.allowed_scopes}))
        if not scopes: raise IdentityFederationError("allowed_scopes required")
        object.__setattr__(self,"allowed_scopes",scopes); object.__setattr__(self,"mapping_evidence_digest",_sha("mapping_evidence_digest",self.mapping_evidence_digest))

@dataclass(frozen=True,slots=True)
class FederatedSessionEvidence:
    session_id:str; local_principal_id:str; tenant_id:str; issuer_id:str; granted_scopes:tuple[str,...]; issued_at_ns:int; expires_at_ns:int; revocation_epoch:int
    def __post_init__(self):
        for n in ("session_id","local_principal_id","tenant_id","issuer_id"): object.__setattr__(self,n,_token(n,getattr(self,n)))
        scopes=tuple(sorted({_token("scope",s) for s in self.granted_scopes}))
        if not scopes: raise IdentityFederationError("granted_scopes required")
        object.__setattr__(self,"granted_scopes",scopes)
        for n in ("issued_at_ns","expires_at_ns","revocation_epoch"):
            v=getattr(self,n)
            if isinstance(v,bool) or not isinstance(v,int) or v<0: raise IdentityFederationError(f"{n} must be non-negative integer")
        if self.expires_at_ns<=self.issued_at_ns: raise IdentityFederationError("session expiration must follow issuance")

@dataclass(frozen=True,slots=True)
class FederationDecision:
    allowed:bool; reasons:tuple[str,...]; effective_scopes:tuple[str,...]; session_digest:str|None
    def __post_init__(self):
        if not isinstance(self.allowed,bool): raise IdentityFederationError("allowed must be boolean")
        object.__setattr__(self,"reasons",tuple(sorted({_token("reason",r,128) for r in self.reasons}))); object.__setattr__(self,"effective_scopes",tuple(sorted({_token("scope",s) for s in self.effective_scopes})))
        if self.session_digest is not None: object.__setattr__(self,"session_digest",_sha("session_digest",self.session_digest))
        if self.allowed and self.reasons: raise IdentityFederationError("allowed federation cannot retain denial reasons")
        if not self.allowed and self.effective_scopes: raise IdentityFederationError("denied federation cannot retain scopes")
    @property
    def digest(self)->str:return _digest({"allowed":self.allowed,"reasons":list(self.reasons),"effective_scopes":list(self.effective_scopes),"session_digest":self.session_digest})

def authorize_federated_session(*,mapping:FederatedPrincipalMapping,session:FederatedSessionEvidence,requested_scopes:tuple[str,...],now_ns:int,current_revocation_epoch:int)->FederationDecision:
    reasons=[]
    if session.local_principal_id!=mapping.local_principal_id or session.tenant_id!=mapping.tenant_id or session.issuer_id!=mapping.issuer_id: reasons.append("principal-mapping-mismatch")
    if now_ns<session.issued_at_ns or now_ns>=session.expires_at_ns: reasons.append("session-expired-or-not-yet-valid")
    if session.revocation_epoch!=current_revocation_epoch: reasons.append("session-revoked")
    requested=set(requested_scopes)
    if not requested.issubset(set(mapping.allowed_scopes)): reasons.append("requested-scope-not-mapped")
    if not requested.issubset(set(session.granted_scopes)): reasons.append("requested-scope-not-in-session")
    if reasons: return FederationDecision(False,tuple(reasons),(),None)
    session_digest=_digest({"session_id":session.session_id,"principal":session.local_principal_id,"tenant":session.tenant_id,"issuer":session.issuer_id,"scopes":list(session.granted_scopes),"issued_at_ns":session.issued_at_ns,"expires_at_ns":session.expires_at_ns,"revocation_epoch":session.revocation_epoch})
    return FederationDecision(True,(),tuple(sorted(requested)),session_digest)
