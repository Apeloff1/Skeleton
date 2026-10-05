"""Identity-safe experiment comparison for VOL-214."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,math

class ExperimentComparisonError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>256: raise ExperimentComparisonError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ExperimentComparisonError(f"{n} must be lowercase sha256")
    return v
def _finite(n:str,v:object)->float:
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(float(v)): raise ExperimentComparisonError(f"{n} must be finite")
    return float(v)
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ExperimentMetric:
    name:str; value:float
    def __post_init__(self): object.__setattr__(self,"name",_token("name",self.name)); object.__setattr__(self,"value",_finite("value",self.value))

@dataclass(frozen=True,slots=True)
class ExperimentSnapshot:
    experiment_id:str; protocol_id:str; dataset_digest:str; benchmark_revision:str; metrics:tuple[ExperimentMetric,...]
    def __post_init__(self):
        object.__setattr__(self,"experiment_id",_token("experiment_id",self.experiment_id)); object.__setattr__(self,"protocol_id",_token("protocol_id",self.protocol_id))
        object.__setattr__(self,"dataset_digest",_sha("dataset_digest",self.dataset_digest)); object.__setattr__(self,"benchmark_revision",_sha("benchmark_revision",self.benchmark_revision))
        if not self.metrics: raise ExperimentComparisonError("metrics required")
        names=[m.name for m in self.metrics]
        if len(names)!=len(set(names)): raise ExperimentComparisonError("metric names must be unique")
        object.__setattr__(self,"metrics",tuple(sorted(self.metrics,key=lambda m:m.name)))
    @property
    def digest(self)->str: return _digest({"experiment_id":self.experiment_id,"protocol_id":self.protocol_id,"dataset_digest":self.dataset_digest,"benchmark_revision":self.benchmark_revision,"metrics":[[m.name,m.value] for m in self.metrics]})

@dataclass(frozen=True,slots=True)
class ExperimentComparison:
    baseline_digest:str; candidate_digest:str; deltas:tuple[tuple[str,float],...]; comparable:bool=True; promotion_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"baseline_digest",_sha("baseline_digest",self.baseline_digest)); object.__setattr__(self,"candidate_digest",_sha("candidate_digest",self.candidate_digest))
        if self.comparable is not True: raise ExperimentComparisonError("comparison receipt requires comparable experiments")
        names=[n for n,_ in self.deltas]
        if len(names)!=len(set(names)): raise ExperimentComparisonError("delta metric names must be unique")
        object.__setattr__(self,"deltas",tuple(sorted((_token("metric",n),_finite("delta",v)) for n,v in self.deltas)))
        if self.promotion_authority is not False: raise ExperimentComparisonError("comparison cannot grant promotion authority")

def compare_experiments(baseline:ExperimentSnapshot,candidate:ExperimentSnapshot)->ExperimentComparison:
    if baseline.protocol_id!=candidate.protocol_id or baseline.dataset_digest!=candidate.dataset_digest or baseline.benchmark_revision!=candidate.benchmark_revision:
        raise ExperimentComparisonError("experiments require identical protocol, dataset, and benchmark revision")
    left={m.name:m.value for m in baseline.metrics}; right={m.name:m.value for m in candidate.metrics}
    if set(left)!=set(right): raise ExperimentComparisonError("experiments require identical metric sets")
    return ExperimentComparison(baseline.digest,candidate.digest,tuple((name,right[name]-left[name]) for name in sorted(left)))
