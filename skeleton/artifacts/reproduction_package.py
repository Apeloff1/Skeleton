"""Portable reproduction-package contracts for VOL-213."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from typing import Iterable

class ReproductionPackageError(ValueError): pass
_KINDS=frozenset({"input","dataset","config","code","model","output","report"})

def _token(name:str,value:object)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>1024: raise ReproductionPackageError(f"{name} must be non-empty normalized text")
    return value
def _sha(name:str,value:object)->str:
    if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value): raise ReproductionPackageError(f"{name} must be lowercase sha256")
    return value
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ReproductionArtifact:
    logical_path:str; kind:str; digest:str
    def __post_init__(self):
        object.__setattr__(self,"logical_path",_token("logical_path",self.logical_path))
        kind=_token("kind",self.kind)
        if kind not in _KINDS: raise ReproductionPackageError("unknown reproduction artifact kind")
        object.__setattr__(self,"kind",kind); object.__setattr__(self,"digest",_sha("digest",self.digest))
    @property
    def identity(self)->tuple[str,str]: return (self.logical_path,self.kind)

@dataclass(frozen=True,slots=True)
class ReproductionPackage:
    package_id:str; experiment_id:str; source_revision:str; environment_digest:str; artifacts:tuple[ReproductionArtifact,...]; commands:tuple[str,...]; deterministic_seed:int|None=None; production_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"package_id",_token("package_id",self.package_id)); object.__setattr__(self,"experiment_id",_token("experiment_id",self.experiment_id))
        rev=_token("source_revision",self.source_revision).lower()
        if len(rev)!=40 or any(c not in "0123456789abcdef" for c in rev): raise ReproductionPackageError("source_revision must be a 40-character lowercase Git SHA")
        object.__setattr__(self,"source_revision",rev); object.__setattr__(self,"environment_digest",_sha("environment_digest",self.environment_digest))
        if not self.artifacts: raise ReproductionPackageError("reproduction package requires artifacts")
        ids=[a.identity for a in self.artifacts]
        if len(ids)!=len(set(ids)): raise ReproductionPackageError("artifact identities must be unique")
        commands=tuple(_token("command",c) for c in self.commands)
        if not commands: raise ReproductionPackageError("commands required")
        object.__setattr__(self,"artifacts",tuple(sorted(self.artifacts,key=lambda a:a.identity))); object.__setattr__(self,"commands",commands)
        if self.deterministic_seed is not None and (isinstance(self.deterministic_seed,bool) or not isinstance(self.deterministic_seed,int) or self.deterministic_seed<0): raise ReproductionPackageError("deterministic_seed must be non-negative integer")
        if self.production_authority is not False: raise ReproductionPackageError("reproduction package cannot grant production authority")
    @property
    def digest(self)->str:
        return _digest({"package_id":self.package_id,"experiment_id":self.experiment_id,"source_revision":self.source_revision,"environment_digest":self.environment_digest,"artifacts":[{"path":a.logical_path,"kind":a.kind,"digest":a.digest} for a in self.artifacts],"commands":list(self.commands),"deterministic_seed":self.deterministic_seed,"production_authority":False})
