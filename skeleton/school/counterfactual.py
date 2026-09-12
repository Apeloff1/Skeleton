"""Deterministic counterfactual policy competition for Jeeves."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence
class CandidateAction(str, Enum):
    REPAIR="repair"; RETRIEVE="retrieve"; PRACTICE="practice"; CHALLENGE="challenge"; TRANSFER="transfer"; PAUSE="pause"
@dataclass(frozen=True)
class PolicyCandidate:
    action:CandidateAction; learning_value:float; evidence_fit:float; risk:float; effort:float; rationale:tuple[str,...]=()
    def __post_init__(self)->None:
        for name in ("learning_value","evidence_fit","risk","effort"):
            if not 0.0<=getattr(self,name)<=1.0: raise ValueError(f"{name} must be in [0, 1]")
    @property
    def score(self)->float: return .40*self.learning_value+.35*self.evidence_fit-.20*self.risk-.05*self.effort
    def calibrated_score(self,reliability:float=.5)->float:
        reliability=max(0.,min(1.,reliability)); return .85*self.score+.15*(reliability-.5)
@dataclass(frozen=True)
class CounterfactualResult:
    selected:PolicyCandidate; rejected:tuple[PolicyCandidate,...]; margin:float; rationale:tuple[str,...]; reliability:Mapping[str,float]|None=None
def compete(candidates:Sequence[PolicyCandidate],*,reliability:Mapping[str,float]|None=None)->CounterfactualResult:
    if not candidates: raise ValueError("at least one policy candidate is required")
    reliability=reliability or {}
    ranked=sorted(candidates,key=lambda x:(-x.calibrated_score(float(reliability.get(x.action.value,.5))),x.action.value))
    selected=ranked[0]; selected_score=selected.calibrated_score(float(reliability.get(selected.action.value,.5))); second=ranked[1].calibrated_score(float(reliability.get(ranked[1].action.value,.5))) if len(ranked)>1 else selected_score; margin=selected_score-second
    rationale=selected.rationale+(f"selected by calibrated score={selected_score:.4f}",f"selection margin={margin:.4f}",f"calibrated reliability={float(reliability.get(selected.action.value,.5)):.3f}")
    return CounterfactualResult(selected,tuple(ranked[1:]),margin,rationale,dict(sorted(reliability.items())))
def default_candidates(*,mastery:float,contradiction:float,energy:float,transfer_ready:bool)->tuple[PolicyCandidate,...]:
    mastery=max(0.,min(1.,mastery)); contradiction=max(0.,min(1.,contradiction)); energy=max(0.,min(1.,energy))
    return (PolicyCandidate(CandidateAction.REPAIR,.75*contradiction,.95*contradiction,.05,.45,("repair is favored by conflicting evidence",)),PolicyCandidate(CandidateAction.RETRIEVE,.55*(1-mastery),.70,.10,.30,("retrieval strengthens uncertain retention",)),PolicyCandidate(CandidateAction.PRACTICE,.80*(1-mastery),.75,.15,.50,("practice consolidates the current skill",)),PolicyCandidate(CandidateAction.CHALLENGE,mastery,.80*mastery*(1-contradiction),.55,.85,("challenge tests the upper boundary of mastery",)),PolicyCandidate(CandidateAction.TRANSFER,.90*mastery if transfer_ready else .25*mastery,.90*mastery*(1-contradiction),.45,.75,("transfer tests generalization",)),PolicyCandidate(CandidateAction.PAUSE,.25*(1-energy),.90 if energy<.25 else .20,.02,.05,("pause protects learning quality when energy is low",)))
