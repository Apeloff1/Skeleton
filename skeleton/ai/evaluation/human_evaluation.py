"""Independent human-evaluation evidence contracts for VOL-220."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class HumanEvaluationError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise HumanEvaluationError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise HumanEvaluationError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class RubricCriterion:
    criterion_id:str; description:str; min_score:int; max_score:int; weight_ppm:int
    def __post_init__(self):
        object.__setattr__(self,"criterion_id",_token("criterion_id",self.criterion_id)); object.__setattr__(self,"description",_token("description",self.description))
        for n in ("min_score","max_score","weight_ppm"):
            if isinstance(getattr(self,n),bool) or not isinstance(getattr(self,n),int): raise HumanEvaluationError(f"{n} must be integer")
        if self.max_score<=self.min_score: raise HumanEvaluationError("max_score must exceed min_score")
        if not 0<self.weight_ppm<=1_000_000: raise HumanEvaluationError("weight_ppm out of range")

@dataclass(frozen=True,slots=True)
class HumanJudgment:
    item_id:str; reviewer_id:str; criterion_id:str; score:int; evidence_digest:str
    def __post_init__(self):
        for n in ("item_id","reviewer_id","criterion_id"): object.__setattr__(self,n,_token(n,getattr(self,n)))
        if isinstance(self.score,bool) or not isinstance(self.score,int): raise HumanEvaluationError("score must be integer")
        object.__setattr__(self,"evidence_digest",_sha("evidence_digest",self.evidence_digest))

@dataclass(frozen=True,slots=True)
class HumanEvaluationReport:
    evaluation_id:str; rubric:tuple[RubricCriterion,...]; judgments:tuple[HumanJudgment,...]; aggregate_score_ppm:int; reviewer_count:int; quality_vector_digest:str; promotion_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"evaluation_id",_token("evaluation_id",self.evaluation_id)); object.__setattr__(self,"quality_vector_digest",_sha("quality_vector_digest",self.quality_vector_digest))
        if not self.rubric or not self.judgments: raise HumanEvaluationError("rubric and judgments required")
        criteria={c.criterion_id:c for c in self.rubric}
        if len(criteria)!=len(self.rubric): raise HumanEvaluationError("criterion ids must be unique")
        reviewers={j.reviewer_id for j in self.judgments}
        if len(reviewers)<2: raise HumanEvaluationError("human evaluation requires at least two independent reviewers")
        if self.reviewer_count!=len(reviewers): raise HumanEvaluationError("reviewer_count must match judgment evidence")
        for j in self.judgments:
            criterion=criteria.get(j.criterion_id)
            if criterion is None: raise HumanEvaluationError("judgment references unknown criterion")
            if not criterion.min_score<=j.score<=criterion.max_score: raise HumanEvaluationError("judgment score outside rubric range")
        by_item={}
        for j in self.judgments: by_item.setdefault(j.item_id,set()).add(j.reviewer_id)
        if any(len(v)<2 for v in by_item.values()): raise HumanEvaluationError("every item requires two independent reviewers")
        total_weight=0; weighted=0
        for j in self.judgments:
            c=criteria[j.criterion_id]; normalized=(j.score-c.min_score)/(c.max_score-c.min_score)
            weighted+=round(normalized*c.weight_ppm); total_weight+=c.weight_ppm
        expected=round(weighted/total_weight*1_000_000)
        if self.aggregate_score_ppm!=expected: raise HumanEvaluationError("aggregate_score_ppm must match judgments")
        if self.promotion_authority is not False: raise HumanEvaluationError("human evaluation report cannot grant promotion authority")
        object.__setattr__(self,"rubric",tuple(sorted(self.rubric,key=lambda c:c.criterion_id))); object.__setattr__(self,"judgments",tuple(sorted(self.judgments,key=lambda j:(j.item_id,j.reviewer_id,j.criterion_id))))
    @property
    def digest(self)->str: return _digest({"evaluation_id":self.evaluation_id,"rubric":[{"id":c.criterion_id,"min":c.min_score,"max":c.max_score,"weight_ppm":c.weight_ppm} for c in self.rubric],"judgments":[{"item":j.item_id,"reviewer":j.reviewer_id,"criterion":j.criterion_id,"score":j.score,"evidence":j.evidence_digest} for j in self.judgments],"aggregate_score_ppm":self.aggregate_score_ppm,"reviewer_count":self.reviewer_count,"quality_vector_digest":self.quality_vector_digest,"promotion_authority":False})

def build_human_report(*,evaluation_id:str,rubric:tuple[RubricCriterion,...],judgments:tuple[HumanJudgment,...],quality_vector_digest:str)->HumanEvaluationReport:
    reviewers={j.reviewer_id for j in judgments}; criteria={c.criterion_id:c for c in rubric}; total_weight=0; weighted=0
    for j in judgments:
        c=criteria.get(j.criterion_id)
        if c is None: raise HumanEvaluationError("judgment references unknown criterion")
        weighted+=round((j.score-c.min_score)/(c.max_score-c.min_score)*c.weight_ppm); total_weight+=c.weight_ppm
    aggregate=round(weighted/total_weight*1_000_000) if total_weight else 0
    return HumanEvaluationReport(evaluation_id,rubric,judgments,aggregate,len(reviewers),quality_vector_digest)
