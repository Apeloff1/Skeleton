"""Deployment profile contracts for VOL-231/232."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class DeploymentProfileError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise DeploymentProfileError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise DeploymentProfileError(f"{n} must be lowercase sha256")
    return v
def _pos(n:str,v:object)->int:
    if isinstance(v,bool) or not isinstance(v,int) or v<=0: raise DeploymentProfileError(f"{n} must be positive")
    return v
def _digest(v:object)->str:return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class EdgeResourceTier:
    tier_id:str; memory_mib:int; storage_mib:int; accelerator_class:str; max_context_tokens:int
    def __post_init__(self):
        object.__setattr__(self,"tier_id",_token("tier_id",self.tier_id)); object.__setattr__(self,"accelerator_class",_token("accelerator_class",self.accelerator_class))
        for n in ("memory_mib","storage_mib","max_context_tokens"): object.__setattr__(self,n,_pos(n,getattr(self,n)))

@dataclass(frozen=True,slots=True)
class EdgeDeploymentProfile:
    profile_id:str; resource_tier:EdgeResourceTier; allowed_model_classes:tuple[str,...]; router_policy_digest:str; local_storage_required:bool; network_optional:bool
    def __post_init__(self):
        object.__setattr__(self,"profile_id",_token("profile_id",self.profile_id))
        if not isinstance(self.resource_tier,EdgeResourceTier): raise DeploymentProfileError("resource_tier required")
        models=tuple(sorted({_token("model_class",m) for m in self.allowed_model_classes}))
        if not models: raise DeploymentProfileError("allowed_model_classes required")
        object.__setattr__(self,"allowed_model_classes",models); object.__setattr__(self,"router_policy_digest",_sha("router_policy_digest",self.router_policy_digest))
        if not isinstance(self.local_storage_required,bool) or not isinstance(self.network_optional,bool): raise DeploymentProfileError("deployment flags must be boolean")
    @property
    def digest(self)->str:return _digest({"kind":"edge","profile_id":self.profile_id,"tier":{"id":self.resource_tier.tier_id,"memory_mib":self.resource_tier.memory_mib,"storage_mib":self.resource_tier.storage_mib,"accelerator_class":self.resource_tier.accelerator_class,"max_context_tokens":self.resource_tier.max_context_tokens},"allowed_model_classes":list(self.allowed_model_classes),"router_policy_digest":self.router_policy_digest,"local_storage_required":self.local_storage_required,"network_optional":self.network_optional})

@dataclass(frozen=True,slots=True)
class EnterpriseTopology:
    topology_id:str; zones:tuple[str,...]; minimum_replicas:int; tenant_isolation_required:bool; audit_required:bool
    def __post_init__(self):
        object.__setattr__(self,"topology_id",_token("topology_id",self.topology_id))
        zones=tuple(sorted({_token("zone",z) for z in self.zones}))
        if len(zones)<2: raise DeploymentProfileError("enterprise topology requires at least two zones")
        object.__setattr__(self,"zones",zones); object.__setattr__(self,"minimum_replicas",_pos("minimum_replicas",self.minimum_replicas))
        if self.minimum_replicas<2: raise DeploymentProfileError("enterprise topology requires redundant replicas")
        if self.tenant_isolation_required is not True or self.audit_required is not True: raise DeploymentProfileError("enterprise topology must require isolation and audit")

@dataclass(frozen=True,slots=True)
class EnterpriseDeploymentProfile:
    profile_id:str; topology:EnterpriseTopology; security_boundary_digest:str; acceptance_evidence_digest:str; admin_plane_digest:str; production_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"profile_id",_token("profile_id",self.profile_id))
        if not isinstance(self.topology,EnterpriseTopology): raise DeploymentProfileError("topology required")
        for n in ("security_boundary_digest","acceptance_evidence_digest","admin_plane_digest"): object.__setattr__(self,n,_sha(n,getattr(self,n)))
        if self.production_authority is not False: raise DeploymentProfileError("deployment profile cannot grant production authority")
    @property
    def digest(self)->str:return _digest({"kind":"enterprise","profile_id":self.profile_id,"topology":{"id":self.topology.topology_id,"zones":list(self.topology.zones),"minimum_replicas":self.topology.minimum_replicas,"tenant_isolation_required":True,"audit_required":True},"security_boundary_digest":self.security_boundary_digest,"acceptance_evidence_digest":self.acceptance_evidence_digest,"admin_plane_digest":self.admin_plane_digest,"production_authority":False})
