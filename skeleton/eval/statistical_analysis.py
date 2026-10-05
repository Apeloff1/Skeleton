"""Approved deterministic statistical analysis contracts for VOL-215."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,math,statistics

class StatisticalAnalysisError(ValueError): pass
_APPROVED=frozenset({"descriptive","paired_difference"})

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>256: raise StatisticalAnalysisError(f"{n} must be non-empty normalized text")
    return v
def _values(values:tuple[float,...])->tuple[float,...]:
    if not isinstance(values,tuple) or not values: raise StatisticalAnalysisError("sample values must be a non-empty tuple")
    out=tuple(float(v) for v in values)
    if any(not math.isfinite(v) for v in out): raise StatisticalAnalysisError("sample values must be finite")
    return out
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class SampleSeries:
    series_id:str; benchmark_id:str; metric_name:str; values:tuple[float,...]
    def __post_init__(self):
        for n in ("series_id","benchmark_id","metric_name"): object.__setattr__(self,n,_token(n,getattr(self,n)))
        object.__setattr__(self,"values",_values(self.values))
    @property
    def digest(self)->str: return _digest({"series_id":self.series_id,"benchmark_id":self.benchmark_id,"metric_name":self.metric_name,"values":list(self.values)})

@dataclass(frozen=True,slots=True)
class StatisticalAnalysis:
    method:str; baseline_digest:str; candidate_digest:str|None; sample_count:int; mean:float; median:float; stdev:float; effect:float|None
    def __post_init__(self):
        method=_token("method",self.method)
        if method not in _APPROVED: raise StatisticalAnalysisError("unapproved statistical method")
        object.__setattr__(self,"method",method)
        for name in ("baseline_digest",):
            v=getattr(self,name)
            if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise StatisticalAnalysisError(f"{name} must be lowercase sha256")
        if self.candidate_digest is not None and (len(self.candidate_digest)!=64 or any(c not in "0123456789abcdef" for c in self.candidate_digest)): raise StatisticalAnalysisError("candidate_digest must be lowercase sha256")
        if isinstance(self.sample_count,bool) or not isinstance(self.sample_count,int) or self.sample_count<=0: raise StatisticalAnalysisError("sample_count must be positive")
        for n in ("mean","median","stdev"):
            if not math.isfinite(float(getattr(self,n))): raise StatisticalAnalysisError(f"{n} must be finite")
        if self.effect is not None and not math.isfinite(float(self.effect)): raise StatisticalAnalysisError("effect must be finite")
    @property
    def digest(self)->str: return _digest({"method":self.method,"baseline_digest":self.baseline_digest,"candidate_digest":self.candidate_digest,"sample_count":self.sample_count,"mean":self.mean,"median":self.median,"stdev":self.stdev,"effect":self.effect})

def summarize(series:SampleSeries)->StatisticalAnalysis:
    vals=series.values
    return StatisticalAnalysis("descriptive",series.digest,None,len(vals),statistics.fmean(vals),statistics.median(vals),statistics.stdev(vals) if len(vals)>1 else 0.0,None)

def paired_difference(baseline:SampleSeries,candidate:SampleSeries)->StatisticalAnalysis:
    if baseline.benchmark_id!=candidate.benchmark_id or baseline.metric_name!=candidate.metric_name: raise StatisticalAnalysisError("paired analysis requires identical benchmark and metric identity")
    if len(baseline.values)!=len(candidate.values): raise StatisticalAnalysisError("paired analysis requires equal sample counts")
    deltas=tuple(c-b for b,c in zip(baseline.values,candidate.values))
    return StatisticalAnalysis("paired_difference",baseline.digest,candidate.digest,len(deltas),statistics.fmean(deltas),statistics.median(deltas),statistics.stdev(deltas) if len(deltas)>1 else 0.0,statistics.fmean(deltas))
