"""Synthetic records with permanent origin and diversity/validity/leakage/bias gates."""
from dataclasses import dataclass
import hashlib,json
class SyntheticDataError(ValueError): pass
def _d(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
@dataclass(frozen=True, slots=True)
class SyntheticJob: job_id:str; generator_id:str; generator_version:str; config_digest:str; reference_dataset_ref:str
@dataclass(frozen=True, slots=True)
class SyntheticRecord: record_id:str; job_id:str; content_digest:str; group_label:str; parent_refs:tuple[str,...]; origin:str="synthetic"
@dataclass(frozen=True, slots=True)
class SyntheticQuality: record_count:int; diversity_ratio:float; validity_ratio:float; memorization_ratio:float; max_group_share:float; promotion_allowed:bool
class SyntheticDataFactory:
    def __init__(self,job):
        if not job.job_id or len(job.config_digest)!=64: raise SyntheticDataError("invalid job")
        self.job=job; self._records={}
    def record(self,*,record_id,value,group_label,parent_refs):
        parents=tuple(sorted(set(parent_refs)))
        if not record_id or not group_label or not parents: raise SyntheticDataError("provenance required")
        r=SyntheticRecord(record_id,self.job.job_id,_d(value),group_label,parents,"synthetic"); old=self._records.get(record_id)
        if old is not None and old!=r: raise SyntheticDataError("identity cannot rebind")
        self._records[record_id]=r; return r
    def evaluate(self,*,reference_content_digests,valid_record_ids,min_diversity=.8,min_validity=.95,max_memorization=.05,max_group_share=.8):
        rows=tuple(self._records.values())
        if not rows: raise SyntheticDataError("empty set")
        digests=[r.content_digest for r in rows]; refs=set(reference_content_digests); valid=set(valid_record_ids); groups={}
        for r in rows: groups[r.group_label]=groups.get(r.group_label,0)+1
        diversity=len(set(digests))/len(rows); validity=sum(r.record_id in valid for r in rows)/len(rows); memorization=sum(d in refs for d in digests)/len(rows); share=max(groups.values())/len(rows)
        return SyntheticQuality(len(rows),diversity,validity,memorization,share,diversity>=min_diversity and validity>=min_validity and memorization<=max_memorization and share<=max_group_share)
