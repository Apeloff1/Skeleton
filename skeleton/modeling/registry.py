"""Content-addressed model-development registry with fail-closed lineage."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from hashlib import sha256
import json, math, re
from types import MappingProxyType
from typing import Any, Mapping

_ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"); _HEX=re.compile(r"^[0-9a-f]{64}$")
MAX_RECORDS=10_000; MAX_LINKS=64
class RegistryError(ValueError): pass
class CollisionError(RegistryError): pass
class LineageError(RegistryError): pass

def _id(v,name):
    if not isinstance(v,str) or not _ID.fullmatch(v): raise RegistryError(f"invalid {name}")
    return v
def _digest(v,name):
    if not isinstance(v,str) or not _HEX.fullmatch(v): raise RegistryError(f"invalid {name}")
    return v
def _freeze(v):
    if v is None or isinstance(v,(str,bool,int)): return v
    if isinstance(v,float):
        if not math.isfinite(v): raise RegistryError("non-finite metadata")
        return v
    if isinstance(v,Mapping): return MappingProxyType({str(k):_freeze(x) for k,x in sorted(v.items(),key=lambda p:str(p[0]))})
    if isinstance(v,(list,tuple)): return tuple(_freeze(x) for x in v)
    raise RegistryError("metadata must be canonical JSON")
def _plain(v):
    if isinstance(v,Mapping): return {k:_plain(x) for k,x in sorted(v.items())}
    if isinstance(v,tuple): return [_plain(x) for x in v]
    return v
def canonical_digest(v):
    return sha256(json.dumps(_plain(v),sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True)
class DatasetManifest:
    dataset_id:str; content_digest:str; rights:str; integrity_digest:str; pii_policy:str
    dedup_digest:str; contamination_digest:str; sources:tuple[str,...]; metadata:Mapping[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        _id(self.dataset_id,"dataset_id")
        for n in ("content_digest","integrity_digest","dedup_digest","contamination_digest"): _digest(getattr(self,n),n)
        if self.rights not in {"owned","licensed","public-domain","research-restricted"}: raise RegistryError("invalid rights")
        if self.pii_policy not in {"none","redacted","consented","restricted"}: raise RegistryError("invalid pii policy")
        if not self.sources or len(self.sources)>MAX_LINKS: raise RegistryError("sources required/bounded")
        if len(set(self.sources))!=len(self.sources): raise RegistryError("duplicate source")
        object.__setattr__(self,"sources",tuple(sorted(_id(x,"source") for x in self.sources)))
        object.__setattr__(self,"metadata",_freeze(self.metadata))
    def to_dict(self): return {"dataset_id":self.dataset_id,"content_digest":self.content_digest,"rights":self.rights,"integrity_digest":self.integrity_digest,"pii_policy":self.pii_policy,"dedup_digest":self.dedup_digest,"contamination_digest":self.contamination_digest,"sources":list(self.sources),"metadata":_plain(self.metadata)}
    @property
    def manifest_digest(self): return canonical_digest(self.to_dict())

@dataclass(frozen=True)
class TrainingRun:
    run_id:str; dataset_digests:tuple[str,...]; code_digest:str; config_digest:str; hardware_digest:str; seed:int
    parent_artifact_digests:tuple[str,...]=(); status:str="candidate"
    def __post_init__(self):
        _id(self.run_id,"run_id")
        if not self.dataset_digests or len(self.dataset_digests)>MAX_LINKS: raise RegistryError("dataset lineage required/bounded")
        if len(set(self.dataset_digests))!=len(self.dataset_digests): raise RegistryError("duplicate dataset")
        if len(set(self.parent_artifact_digests))!=len(self.parent_artifact_digests) or len(self.parent_artifact_digests)>MAX_LINKS: raise RegistryError("invalid parents")
        object.__setattr__(self,"dataset_digests",tuple(sorted(_digest(x,"dataset digest") for x in self.dataset_digests)))
        object.__setattr__(self,"parent_artifact_digests",tuple(sorted(_digest(x,"parent artifact") for x in self.parent_artifact_digests)))
        for n in ("code_digest","config_digest","hardware_digest"): _digest(getattr(self,n),n)
        if not isinstance(self.seed,int) or isinstance(self.seed,bool): raise RegistryError("seed must be integer")
        if self.status not in {"candidate","failed","completed"}: raise RegistryError("invalid run status")
    def to_dict(self): return {"run_id":self.run_id,"dataset_digests":list(self.dataset_digests),"code_digest":self.code_digest,"config_digest":self.config_digest,"hardware_digest":self.hardware_digest,"seed":self.seed,"parent_artifact_digests":list(self.parent_artifact_digests),"status":self.status}
    @property
    def run_digest(self): return canonical_digest(self.to_dict())

@dataclass(frozen=True)
class ModelArtifact:
    artifact_id:str; content_digest:str; training_run_digest:str; evaluation_digest:str; format:str
    metadata:Mapping[str,Any]=field(default_factory=dict); authority_scope:str="research-only"
    def __post_init__(self):
        _id(self.artifact_id,"artifact_id"); _id(self.format,"format")
        for n in ("content_digest","training_run_digest","evaluation_digest"): _digest(getattr(self,n),n)
        if self.authority_scope!="research-only": raise RegistryError("registry cannot grant production authority")
        object.__setattr__(self,"metadata",_freeze(self.metadata))
    def to_dict(self): return {"artifact_id":self.artifact_id,"content_digest":self.content_digest,"training_run_digest":self.training_run_digest,"evaluation_digest":self.evaluation_digest,"format":self.format,"metadata":_plain(self.metadata),"authority_scope":self.authority_scope}
    @property
    def artifact_digest(self): return canonical_digest(self.to_dict())

@dataclass(frozen=True)
class TrainingLineage:
    artifact_digest:str; run_digest:str; dataset_digests:tuple[str,...]; code_digest:str; config_digest:str; hardware_digest:str; evaluation_digest:str
    def __post_init__(self):
        _digest(self.artifact_digest,"artifact"); _digest(self.run_digest,"run")
        if not self.dataset_digests or len(self.dataset_digests)>MAX_LINKS: raise RegistryError("invalid dataset lineage")
        object.__setattr__(self,"dataset_digests",tuple(sorted(_digest(x,"dataset") for x in self.dataset_digests)))
        for n in ("code_digest","config_digest","hardware_digest","evaluation_digest"): _digest(getattr(self,n),n)
    @property
    def lineage_digest(self): return canonical_digest(asdict(self))

class ModelDevelopmentRegistry:
    """Append-only bounded evidence registry. No method promotes a model."""
    def __init__(self):
        self._datasets={}; self._runs={}; self._artifacts={}; self._dataset_ids={}; self._run_ids={}; self._artifact_ids={}
    @staticmethod
    def _put(by_digest,by_id,obj,identity,digest):
        old=by_id.get(identity)
        if old is not None:
            if old==obj: return digest
            raise CollisionError(f"identity collision: {identity}")
        prior=by_digest.get(digest)
        if prior is not None and prior!=obj: raise CollisionError("digest collision")
        if len(by_id)>=MAX_RECORDS: raise RegistryError("registry capacity exceeded")
        by_id[identity]=obj; by_digest[digest]=obj; return digest
    def add_dataset(self,d):
        if not isinstance(d,DatasetManifest): raise RegistryError("DatasetManifest required")
        return self._put(self._datasets,self._dataset_ids,d,d.dataset_id,d.manifest_digest)
    def add_run(self,r):
        if not isinstance(r,TrainingRun): raise RegistryError("TrainingRun required")
        if any(x not in self._datasets for x in r.dataset_digests): raise LineageError("unknown dataset lineage")
        if any(x not in self._artifacts for x in r.parent_artifact_digests): raise LineageError("unknown parent artifact")
        return self._put(self._runs,self._run_ids,r,r.run_id,r.run_digest)
    def add_artifact(self,a):
        if not isinstance(a,ModelArtifact): raise RegistryError("ModelArtifact required")
        run=self._runs.get(a.training_run_digest)
        if run is None: raise LineageError("unknown training run")
        if run.status!="completed": raise LineageError("artifact requires completed run")
        return self._put(self._artifacts,self._artifact_ids,a,a.artifact_id,a.artifact_digest)
    def lineage(self,artifact_digest):
        a=self._artifacts.get(_digest(artifact_digest,"artifact digest"))
        if a is None: raise LineageError("unknown artifact")
        r=self._runs.get(a.training_run_digest)
        if r is None: raise LineageError("broken run lineage")
        return TrainingLineage(a.artifact_digest,r.run_digest,r.dataset_digests,r.code_digest,r.config_digest,r.hardware_digest,a.evaluation_digest)
    def verify(self,artifact_digest,lineage):
        if not isinstance(lineage,TrainingLineage): return False
        return self.lineage(artifact_digest)==lineage
    def snapshot_digest(self):
        return canonical_digest({"datasets":sorted(self._datasets),"runs":sorted(self._runs),"artifacts":sorted(self._artifacts)})
