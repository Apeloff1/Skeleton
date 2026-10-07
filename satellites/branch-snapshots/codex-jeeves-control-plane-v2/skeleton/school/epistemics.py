"""Explicit evidence, belief state, contradiction, and misconception lifecycle."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

class EvidencePolarity(str, Enum):
    SUPPORTS="supports"; REFUTES="refutes"; NEUTRAL="neutral"
class MisconceptionStage(str, Enum):
    NONE="none"; DETECTED="detected"; HYPOTHESIS="hypothesis"; REPAIRING="repairing"; REPAIRED="repaired"; PERSISTENT="persistent"
@dataclass(frozen=True)
class EpistemicEvidence:
    evidence_id:str; claim:str; polarity:EvidencePolarity; strength:float=1.0; source_id:str=""; reliability:float=1.0; step:int=0; supersedes:tuple[str,...]=()
    def __post_init__(self):
        for name,value in (("strength",self.strength),("reliability",self.reliability)):
            if not 0<=value<=1: raise ValueError(f"{name} must be in [0, 1]")
    @property
    def weight(self): return self.strength*self.reliability
@dataclass(frozen=True)
class BeliefState:
    claim:str; confidence:float; support:float; refutation:float; evidence_ids:tuple[str,...]=(); last_updated_step:int=0; contradiction:bool=False
@dataclass(frozen=True)
class EpistemicUpdate:
    belief:BeliefState; confidence_delta:float; contradiction:bool; rationale:tuple[str,...]
@dataclass
class EpistemicEngine:
    evidence:dict[str,EpistemicEvidence]=field(default_factory=dict)
    beliefs:dict[str,BeliefState]=field(default_factory=dict)
    misconceptions:dict[str,MisconceptionStage]=field(default_factory=dict)
    def observe(self,item:EpistemicEvidence)->EpistemicUpdate:
        old=self.evidence.get(item.evidence_id)
        if old is not None and old!=item: raise ValueError(f"evidence id collision: {item.evidence_id}")
        self.evidence[item.evidence_id]=item
        active=[e for e in self.evidence.values() if e.claim==item.claim and e.evidence_id not in {s for x in self.evidence.values() for s in x.supersedes}]
        support=sum(e.weight for e in active if e.polarity is EvidencePolarity.SUPPORTS)
        refutation=sum(e.weight for e in active if e.polarity is EvidencePolarity.REFUTES)
        total=support+refutation; raw=support/total if total else .5
        confidence=self._bounded_confidence(raw,support,refutation)
        ids=tuple(e.evidence_id for e in active)
        prior=self.beliefs.get(item.claim)
        belief=BeliefState(item.claim,confidence,support,refutation,ids,max(item.step,prior.last_updated_step if prior else 0),support>0 and refutation>0)
        self.beliefs[item.claim]=belief
        delta=confidence-(prior.confidence if prior else .5)
        rationale=(("supporting evidence increased belief",) if item.polarity is EvidencePolarity.SUPPORTS else ("refuting evidence decreased belief",) if item.polarity is EvidencePolarity.REFUTES else ("neutral evidence preserved belief",))
        if belief.contradiction: rationale += ("support and refutation are simultaneously present",)
        if item.supersedes: rationale += (f"superseded evidence: {','.join(item.supersedes)}",)
        return EpistemicUpdate(belief,delta,belief.contradiction,rationale)
    def decay(self,*,current_step:int,half_life:int=20):
        if half_life<=0: raise ValueError("half_life must be positive")
        result=[]
        for claim,belief in self.beliefs.items():
            age=max(0,current_step-belief.last_updated_step); factor=.5**(age/half_life); centered=.5+(belief.confidence-.5)*factor
            updated=BeliefState(claim,centered,belief.support*factor,belief.refutation*factor,belief.evidence_ids,belief.last_updated_step,belief.contradiction)
            self.beliefs[claim]=updated; result.append(updated)
        return tuple(result)
    def mark_misconception(self,claim,stage): self.misconceptions[claim]=stage
    def repair_signal(self,claim):
        stage=self.misconceptions.get(claim,MisconceptionStage.NONE)
        if stage is MisconceptionStage.PERSISTENT:return "reteach_with_new_representation"
        if stage in {MisconceptionStage.DETECTED,MisconceptionStage.HYPOTHESIS}:return "diagnose_and_test"
        if stage is MisconceptionStage.REPAIRING:return "verify_transfer"
        if stage is MisconceptionStage.REPAIRED:return "schedule_spaced_check"
        return "no_repair_required"
    def contradictions(self): return tuple(b for b in self.beliefs.values() if b.contradiction)
    @staticmethod
    def _bounded_confidence(raw,support,refutation):
        if support and refutation:
            conflict=min(support,refutation)/max(support,refutation); return min(raw,.95-.35*conflict)
        return max(.05,min(.95,raw))
def contradiction_matrix(evidence:Sequence[EpistemicEvidence]):
    by_claim={}
    for item in evidence: by_claim.setdefault(item.claim,set()).add(item.polarity)
    return tuple(sorted((claim,"support/refute") for claim,pol in by_claim.items() if EvidencePolarity.SUPPORTS in pol and EvidencePolarity.REFUTES in pol))
