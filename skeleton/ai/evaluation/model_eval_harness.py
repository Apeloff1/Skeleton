"""Deterministic model evaluation harness for VOL-216."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,math

class ModelEvalError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise ModelEvalError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ModelEvalError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ModelEvalCase:
    case_id:str; input_digest:str; rubric_id:str; weight_ppm:int=1_000_000
    def __post_init__(self):
        object.__setattr__(self,"case_id",_token("case_id",self.case_id)); object.__setattr__(self,"input_digest",_sha("input_digest",self.input_digest)); object.__setattr__(self,"rubric_id",_token("rubric_id",self.rubric_id))
        if isinstance(self.weight_ppm,bool) or not isinstance(self.weight_ppm,int) or not 0<self.weight_ppm<=1_000_000: raise ModelEvalError("weight_ppm must be within (0,1000000]")

@dataclass(frozen=True,slots=True)
class ModelEvalResult:
    case_id:str; model_id:str; score_ppm:int; passed:bool; evidence_digest:str
    def __post_init__(self):
        object.__setattr__(self,"case_id",_token("case_id",self.case_id)); object.__setattr__(self,"model_id",_token("model_id",self.model_id)); object.__setattr__(self,"evidence_digest",_sha("evidence_digest",self.evidence_digest))
        if isinstance(self.score_ppm,bool) or not isinstance(self.score_ppm,int) or not 0<=self.score_ppm<=1_000_000: raise ModelEvalError("score_ppm out of range")
        if not isinstance(self.passed,bool): raise ModelEvalError("passed must be boolean")

@dataclass(frozen=True,slots=True)
class ModelEvaluationReport:
    model_id:str; benchmark_id:str; quality_vector_digest:str; results:tuple[ModelEvalResult,...]; pass_rate_ppm:int; promotion_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"model_id",_token("model_id",self.model_id)); object.__setattr__(self,"benchmark_id",_token("benchmark_id",self.benchmark_id)); object.__setattr__(self,"quality_vector_digest",_sha("quality_vector_digest",self.quality_vector_digest))
        if not self.results: raise ModelEvalError("results required")
        ids=[r.case_id for r in self.results]
        if len(ids)!=len(set(ids)): raise ModelEvalError("case results must be unique")
        if any(r.model_id!=self.model_id for r in self.results): raise ModelEvalError("result model identity mismatch")
        expected=round(sum(1 for r in self.results if r.passed)/len(self.results)*1_000_000)
        if self.pass_rate_ppm!=expected: raise ModelEvalError("pass_rate_ppm must match result evidence")
        if self.promotion_authority is not False: raise ModelEvalError("evaluation report cannot grant promotion authority")
        object.__setattr__(self,"results",tuple(sorted(self.results,key=lambda r:r.case_id)))
    @property
    def digest(self)->str: return _digest({"model_id":self.model_id,"benchmark_id":self.benchmark_id,"quality_vector_digest":self.quality_vector_digest,"results":[{"case":r.case_id,"score_ppm":r.score_ppm,"passed":r.passed,"evidence":r.evidence_digest} for r in self.results],"pass_rate_ppm":self.pass_rate_ppm,"promotion_authority":False})

def build_model_report(*,model_id:str,benchmark_id:str,quality_vector_digest:str,cases:tuple[ModelEvalCase,...],results:tuple[ModelEvalResult,...])->ModelEvaluationReport:
    case_ids={c.case_id for c in cases}
    if case_ids!={r.case_id for r in results}: raise ModelEvalError("results must exactly cover evaluation cases")
    return ModelEvaluationReport(model_id,benchmark_id,quality_vector_digest,results,round(sum(1 for r in results if r.passed)/len(results)*1_000_000))
