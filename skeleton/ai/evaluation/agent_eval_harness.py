"""Scenario-based agent evaluation harness for VOL-217."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class AgentEvalError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise AgentEvalError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise AgentEvalError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class AgentScenario:
    scenario_id:str; objective:str; required_capabilities:tuple[str,...]; max_actions:int
    def __post_init__(self):
        object.__setattr__(self,"scenario_id",_token("scenario_id",self.scenario_id)); object.__setattr__(self,"objective",_token("objective",self.objective))
        caps=tuple(sorted({_token("capability",v) for v in self.required_capabilities}))
        if not caps: raise AgentEvalError("required_capabilities required")
        object.__setattr__(self,"required_capabilities",caps)
        if isinstance(self.max_actions,bool) or not isinstance(self.max_actions,int) or self.max_actions<=0: raise AgentEvalError("max_actions must be positive")

@dataclass(frozen=True,slots=True)
class AgentScenarioResult:
    scenario_id:str; agent_id:str; actions:int; succeeded:bool; violation_codes:tuple[str,...]; performance_evidence_digest:str
    def __post_init__(self):
        object.__setattr__(self,"scenario_id",_token("scenario_id",self.scenario_id)); object.__setattr__(self,"agent_id",_token("agent_id",self.agent_id)); object.__setattr__(self,"performance_evidence_digest",_sha("performance_evidence_digest",self.performance_evidence_digest))
        if isinstance(self.actions,bool) or not isinstance(self.actions,int) or self.actions<0: raise AgentEvalError("actions must be non-negative")
        if not isinstance(self.succeeded,bool): raise AgentEvalError("succeeded must be boolean")
        object.__setattr__(self,"violation_codes",tuple(sorted({_token("violation_code",v) for v in self.violation_codes})))
        if self.succeeded and self.violation_codes: raise AgentEvalError("successful scenario cannot contain violations")

@dataclass(frozen=True,slots=True)
class AgentEvaluationReport:
    agent_id:str; results:tuple[AgentScenarioResult,...]; passed:bool; performance_evidence_digest:str; promotion_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"agent_id",_token("agent_id",self.agent_id)); object.__setattr__(self,"performance_evidence_digest",_sha("performance_evidence_digest",self.performance_evidence_digest))
        if not self.results: raise AgentEvalError("results required")
        if any(r.agent_id!=self.agent_id for r in self.results): raise AgentEvalError("result agent identity mismatch")
        ids=[r.scenario_id for r in self.results]
        if len(ids)!=len(set(ids)): raise AgentEvalError("scenario results must be unique")
        expected=all(r.succeeded and not r.violation_codes for r in self.results)
        if self.passed!=expected: raise AgentEvalError("passed must match scenario evidence")
        if self.promotion_authority is not False: raise AgentEvalError("agent evaluation cannot grant promotion authority")
        object.__setattr__(self,"results",tuple(sorted(self.results,key=lambda r:r.scenario_id)))
    @property
    def digest(self)->str: return _digest({"agent_id":self.agent_id,"results":[{"scenario":r.scenario_id,"actions":r.actions,"succeeded":r.succeeded,"violations":list(r.violation_codes),"evidence":r.performance_evidence_digest} for r in self.results],"passed":self.passed,"performance_evidence_digest":self.performance_evidence_digest,"promotion_authority":False})

def evaluate_agent(*,agent_id:str,scenarios:tuple[AgentScenario,...],results:tuple[AgentScenarioResult,...],performance_evidence_digest:str)->AgentEvaluationReport:
    by={s.scenario_id:s for s in scenarios}
    if set(by)!={r.scenario_id for r in results}: raise AgentEvalError("results must exactly cover scenarios")
    for result in results:
        if result.actions>by[result.scenario_id].max_actions: raise AgentEvalError("scenario exceeded action budget")
    passed=all(r.succeeded and not r.violation_codes for r in results)
    return AgentEvaluationReport(agent_id,results,passed,performance_evidence_digest)
