"""Fail-closed deployment profiles for VOL-229..VOL-232."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Iterable
from .contracts import sha256_json
def _text(v:object,name:str)->str:
 if not isinstance(v,str) or not v.strip(): raise ValueError(f"{name} must be non-empty text")
 return v.strip()
def _digest(v:object,name:str)->str:
 v=_text(v,name)
 if len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ValueError(f"{name} must be lowercase sha256")
 return v
def _unique(values:Iterable[str],name:str)->tuple[str,...]:
 out=tuple(_text(v,name) for v in values)
 if len(out)!=len(set(out)): raise ValueError(f"{name} must be unique")
 return out
class Connectivity(str,Enum): ONLINE="online"; OFFLINE="offline"; AIR_GAPPED="air_gapped"; INTERMITTENT="intermittent"
@dataclass(frozen=True,slots=True)
class OfflineProfile:
 profile_id:str; connectivity:Connectivity; local_capabilities:tuple[str,...]; remote_capabilities:tuple[str,...]; data_revision:str; freshness_observed_at:str
 def __post_init__(self):
  object.__setattr__(self,"profile_id",_text(self.profile_id,"profile_id"))
  if not isinstance(self.connectivity,Connectivity): raise TypeError("connectivity must be Connectivity")
  object.__setattr__(self,"local_capabilities",_unique(self.local_capabilities,"local_capability")); object.__setattr__(self,"remote_capabilities",_unique(self.remote_capabilities,"remote_capability")); object.__setattr__(self,"data_revision",_text(self.data_revision,"data_revision")); object.__setattr__(self,"freshness_observed_at",_text(self.freshness_observed_at,"freshness_observed_at"))
  if self.connectivity in (Connectivity.OFFLINE,Connectivity.AIR_GAPPED) and self.remote_capabilities: raise ValueError("disconnected profile cannot advertise remote capabilities")
@dataclass(frozen=True,slots=True)
class DeferredOperation:
 operation_id:str; payload_digest:str; idempotency_key:str; authority_receipt:str
 def __post_init__(self):
  for n in ("operation_id","idempotency_key","authority_receipt"): object.__setattr__(self,n,_text(getattr(self,n),n))
  object.__setattr__(self,"payload_digest",_digest(self.payload_digest,"payload_digest"))
class SyncState(str,Enum): APPLIED="applied"; CONFLICT="conflict"; REJECTED="rejected"
@dataclass(frozen=True,slots=True)
class SyncReceipt:
 operation_id:str; idempotency_key:str; state:SyncState; remote_revision:str|None
 def __post_init__(self):
  object.__setattr__(self,"operation_id",_text(self.operation_id,"operation_id")); object.__setattr__(self,"idempotency_key",_text(self.idempotency_key,"idempotency_key"))
  if not isinstance(self.state,SyncState): raise TypeError("state must be SyncState")
  if self.remote_revision is not None: object.__setattr__(self,"remote_revision",_text(self.remote_revision,"remote_revision"))
  if self.state is SyncState.APPLIED and self.remote_revision is None: raise ValueError("applied sync requires remote revision")
class DeferredSyncLedger:
 def __init__(self): self._receipts={}
 def reconcile(self,operation:DeferredOperation,*,remote_revision:str|None,conflict:bool=False)->SyncReceipt:
  prior=self._receipts.get(operation.idempotency_key)
  if prior is not None:
   if prior.operation_id!=operation.operation_id: raise ValueError("idempotency key collision")
   return prior
  receipt=SyncReceipt(operation.operation_id,operation.idempotency_key,SyncState.CONFLICT if conflict else SyncState.APPLIED,remote_revision if not conflict else None); self._receipts[operation.idempotency_key]=receipt; return receipt
@dataclass(frozen=True,slots=True)
class AirGapProfile:
 profile_id:str; external_connectors_enabled:bool; egress_enabled:bool; trusted_signer_ids:tuple[str,...]
 def __post_init__(self):
  object.__setattr__(self,"profile_id",_text(self.profile_id,"profile_id")); object.__setattr__(self,"trusted_signer_ids",_unique(self.trusted_signer_ids,"trusted_signer_id"))
  if self.external_connectors_enabled or self.egress_enabled: raise ValueError("air-gap profile must disable connectors and egress by construction")
  if not self.trusted_signer_ids: raise ValueError("air-gap profile requires trusted import signer")
@dataclass(frozen=True,slots=True)
class TransferBundle:
 bundle_id:str; payload_digest:str; manifest_digest:str; signer_id:str; signature_digest:str
 def __post_init__(self):
  object.__setattr__(self,"bundle_id",_text(self.bundle_id,"bundle_id")); object.__setattr__(self,"payload_digest",_digest(self.payload_digest,"payload_digest")); object.__setattr__(self,"manifest_digest",_digest(self.manifest_digest,"manifest_digest")); object.__setattr__(self,"signer_id",_text(self.signer_id,"signer_id")); object.__setattr__(self,"signature_digest",_digest(self.signature_digest,"signature_digest"))
def admit_transfer(profile:AirGapProfile,bundle:TransferBundle)->bool: return bundle.signer_id in profile.trusted_signer_ids
@dataclass(frozen=True,slots=True)
class EdgeProfile:
 profile_id:str; cpu_cores:int; memory_mb:int; storage_mb:int; max_model_memory_mb:int; security_profile:str; connectivity:Connectivity
 def __post_init__(self):
  object.__setattr__(self,"profile_id",_text(self.profile_id,"profile_id"))
  for n in ("cpu_cores","memory_mb","storage_mb","max_model_memory_mb"):
   v=getattr(self,n)
   if isinstance(v,bool) or not isinstance(v,int) or v<=0: raise ValueError(f"{n} must be positive integer")
  object.__setattr__(self,"security_profile",_text(self.security_profile,"security_profile"))
  if not isinstance(self.connectivity,Connectivity): raise TypeError("connectivity must be Connectivity")
  if self.max_model_memory_mb>self.memory_mb: raise ValueError("model memory ceiling cannot exceed node memory")
@dataclass(frozen=True,slots=True)
class EdgeNode:
 node_id:str; profile:EdgeProfile; runtime_revision:str; persisted_state_digest:str
 def __post_init__(self): object.__setattr__(self,"node_id",_text(self.node_id,"node_id")); object.__setattr__(self,"runtime_revision",_text(self.runtime_revision,"runtime_revision")); object.__setattr__(self,"persisted_state_digest",_digest(self.persisted_state_digest,"persisted_state_digest"))
class EnterpriseTopology(str,Enum): SINGLE_TENANT="single_tenant"; MULTI_TENANT="multi_tenant"; HA="ha"
@dataclass(frozen=True,slots=True)
class EnterpriseProfile:
 organization_id:str; topology:EnterpriseTopology; admin_principals:tuple[str,...]; model_authority_principals:tuple[str,...]; policy_revision:str
 def __post_init__(self):
  object.__setattr__(self,"organization_id",_text(self.organization_id,"organization_id"))
  if not isinstance(self.topology,EnterpriseTopology): raise TypeError("topology must be EnterpriseTopology")
  object.__setattr__(self,"admin_principals",_unique(self.admin_principals,"admin_principal")); object.__setattr__(self,"model_authority_principals",_unique(self.model_authority_principals,"model_authority_principal")); object.__setattr__(self,"policy_revision",_text(self.policy_revision,"policy_revision"))
  if set(self.admin_principals)&set(self.model_authority_principals): raise ValueError("organization administration must remain separate from model authority")
 @property
 def identity(self): return sha256_json({"schema":"skeleton.enterprise-profile.v1","organization_id":self.organization_id,"topology":self.topology.value,"admin_principals":list(self.admin_principals),"model_authority_principals":list(self.model_authority_principals),"policy_revision":self.policy_revision})