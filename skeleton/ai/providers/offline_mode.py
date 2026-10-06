"""Explicit offline capability profile for VOL-229."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class OfflineModeError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise OfflineModeError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise OfflineModeError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str:return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class OfflineCapability:
    capability_id:str; requires_local_model:bool; requires_local_storage:bool; network_required:bool=False
    def __post_init__(self):
        object.__setattr__(self,"capability_id",_token("capability_id",self.capability_id))
        if any(not isinstance(getattr(self,n),bool) for n in ("requires_local_model","requires_local_storage","network_required")): raise OfflineModeError("capability flags must be boolean")
        if self.network_required: raise OfflineModeError("offline capability cannot require network")

@dataclass(frozen=True,slots=True)
class OfflineProfile:
    profile_id:str; capabilities:tuple[OfflineCapability,...]; local_model_digest:str|None; local_storage_digest:str|None; egress_disabled:bool=True; provider_calls_allowed:bool=False
    def __post_init__(self):
        object.__setattr__(self,"profile_id",_token("profile_id",self.profile_id))
        if not self.capabilities: raise OfflineModeError("offline capabilities required")
        ids=[c.capability_id for c in self.capabilities]
        if len(ids)!=len(set(ids)): raise OfflineModeError("offline capability ids must be unique")
        if self.local_model_digest is not None: object.__setattr__(self,"local_model_digest",_sha("local_model_digest",self.local_model_digest))
        if self.local_storage_digest is not None: object.__setattr__(self,"local_storage_digest",_sha("local_storage_digest",self.local_storage_digest))
        if any(c.requires_local_model for c in self.capabilities) and self.local_model_digest is None: raise OfflineModeError("local model evidence required")
        if any(c.requires_local_storage for c in self.capabilities) and self.local_storage_digest is None: raise OfflineModeError("local storage evidence required")
        if self.egress_disabled is not True or self.provider_calls_allowed is not False: raise OfflineModeError("offline profile must disable egress/provider calls")
        object.__setattr__(self,"capabilities",tuple(sorted(self.capabilities,key=lambda c:c.capability_id)))
    @property
    def digest(self)->str:return _digest({"profile_id":self.profile_id,"capabilities":[{"id":c.capability_id,"local_model":c.requires_local_model,"local_storage":c.requires_local_storage,"network_required":False} for c in self.capabilities],"local_model_digest":self.local_model_digest,"local_storage_digest":self.local_storage_digest,"egress_disabled":True,"provider_calls_allowed":False})
