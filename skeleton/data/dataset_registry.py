"""Immutable dataset/split registry with rights, retention, PII and contamination gates."""
from dataclasses import dataclass
import hashlib,json
class DatasetRegistryError(ValueError): pass
def _fp(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
@dataclass(frozen=True, slots=True)
class Dataset: dataset_id:str; owner:str
@dataclass(frozen=True, slots=True)
class DatasetVersion: dataset_id:str; version:int; manifest_digest:str; allowed_uses:tuple[str,...]; pii:bool; retention_until_epoch:int|None; contamination_tags:tuple[str,...]
@dataclass(frozen=True, slots=True)
class DatasetSplit: dataset_id:str; version:int; name:str; record_fingerprint:str; record_ids:tuple[str,...]
class DatasetRegistry:
    def __init__(self): self._datasets={}; self._versions={}; self._splits={}
    def register_dataset(self,d):
        if not d.dataset_id or not d.owner: raise DatasetRegistryError("invalid dataset")
        old=self._datasets.get(d.dataset_id)
        if old is not None and old!=d: raise DatasetRegistryError("dataset identity cannot be rebound")
        self._datasets[d.dataset_id]=d
    def register_version(self,*,dataset_id,version,source_refs,allowed_uses,pii,retention_until_epoch,contamination_tags=()):
        if dataset_id not in self._datasets or isinstance(version,bool) or version<1: raise DatasetRegistryError("invalid version")
        refs=tuple(sorted(set(source_refs))); uses=tuple(sorted(set(allowed_uses))); tags=tuple(sorted(set(contamination_tags)))
        if not refs or not uses: raise DatasetRegistryError("refs/uses required")
        v=DatasetVersion(dataset_id,version,_fp([dataset_id,version,refs,uses,bool(pii),retention_until_epoch,tags]),uses,bool(pii),retention_until_epoch,tags); key=(dataset_id,version); old=self._versions.get(key)
        if old is not None and old!=v: raise DatasetRegistryError("dataset version is immutable")
        self._versions[key]=v; return v
    def register_split(self,*,dataset_id,version,name,record_ids):
        if (dataset_id,version) not in self._versions or not name: raise DatasetRegistryError("invalid split")
        ids=tuple(sorted(set(record_ids)))
        for (ds,ver,other),s in self._splits.items():
            if ds==dataset_id and ver==version and other!=name and set(ids)&set(s.record_ids): raise DatasetRegistryError("split leakage detected")
        v=DatasetSplit(dataset_id,version,name,_fp(ids),ids); key=(dataset_id,version,name); old=self._splits.get(key)
        if old is not None and old!=v: raise DatasetRegistryError("split immutable")
        self._splits[key]=v; return v
    def authorize_use(self,*,dataset_id,version,use,current_epoch):
        v=self._versions.get((dataset_id,version))
        if v is None: raise KeyError("dataset version")
        if use not in v.allowed_uses: raise DatasetRegistryError("use not permitted")
        if v.retention_until_epoch is not None and current_epoch>v.retention_until_epoch: raise DatasetRegistryError("retention expired")
        if v.pii and use=="public_export": raise DatasetRegistryError("PII export forbidden")
        if use=="train" and "benchmark" in v.contamination_tags: raise DatasetRegistryError("benchmark contamination")
        return v
