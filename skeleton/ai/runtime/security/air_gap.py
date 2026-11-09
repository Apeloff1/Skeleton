"""Air-gapped package trust workflow for VOL-230."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class AirGapProfileError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise AirGapProfileError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise AirGapProfileError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str:return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class TrustedPackage:
    package_id:str; artifact_digest:str; sbom_digest:str; provenance_digest:str; signature_digest:str
    def __post_init__(self):
        object.__setattr__(self,"package_id",_token("package_id",self.package_id))
        for n in ("artifact_digest","sbom_digest","provenance_digest","signature_digest"): object.__setattr__(self,n,_sha(n,getattr(self,n)))
    @property
    def digest(self)->str:return _digest({"package_id":self.package_id,"artifact_digest":self.artifact_digest,"sbom_digest":self.sbom_digest,"provenance_digest":self.provenance_digest,"signature_digest":self.signature_digest})

@dataclass(frozen=True,slots=True)
class AirGapInstallProfile:
    profile_id:str; trusted_root_digest:str; packages:tuple[TrustedPackage,...]; removable_media_scan_digest:str; network_disabled:bool=True; online_update_allowed:bool=False
    def __post_init__(self):
        object.__setattr__(self,"profile_id",_token("profile_id",self.profile_id)); object.__setattr__(self,"trusted_root_digest",_sha("trusted_root_digest",self.trusted_root_digest)); object.__setattr__(self,"removable_media_scan_digest",_sha("removable_media_scan_digest",self.removable_media_scan_digest))
        if not self.packages: raise AirGapProfileError("air-gap profile requires trusted packages")
        ids=[p.package_id for p in self.packages]
        if len(ids)!=len(set(ids)): raise AirGapProfileError("package ids must be unique")
        object.__setattr__(self,"packages",tuple(sorted(self.packages,key=lambda p:p.package_id)))
        if self.network_disabled is not True or self.online_update_allowed is not False: raise AirGapProfileError("air-gap profile must disable network and online updates")
    @property
    def digest(self)->str:return _digest({"profile_id":self.profile_id,"trusted_root_digest":self.trusted_root_digest,"package_digests":[p.digest for p in self.packages],"removable_media_scan_digest":self.removable_media_scan_digest,"network_disabled":True,"online_update_allowed":False})
