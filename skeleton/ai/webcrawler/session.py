"""Research-session orchestration, receipts and bounded stopping conditions."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass,field
from typing import Iterable
from .core import CrawlEngine,CrawlDocument
from .research import EvidenceSet,ResearchQuery

@dataclass(frozen=True)
class SessionLimits:
    max_steps:int=1000;max_idle_steps:int=20;stop_when_sufficient:bool=True

@dataclass
class ResearchSession:
    query:ResearchQuery;engine:CrawlEngine;limits:SessionLimits=field(default_factory=SessionLimits)
    evidence:EvidenceSet=field(init=False);steps:int=0;idle_steps:int=0;stop_reason:str|None=None
    def __post_init__(self):self.evidence=EvidenceSet(self.query)
    @property
    def session_id(self):return hashlib.sha256(self.query.text.encode()).hexdigest()[:24]
    def run_step(self,*,now:float)->CrawlDocument|None:
        if self.stop_reason:return None
        if self.steps>=self.limits.max_steps:self.stop_reason="step_budget";return None
        if self.engine.budget.exhausted:self.stop_reason="crawl_budget";return None
        doc=self.engine.step(now=now);self.steps+=1
        if doc:self.evidence.add(doc);self.idle_steps=0
        else:self.idle_steps+=1
        if self.limits.stop_when_sufficient and self.evidence.assurance(now=now)["sufficient"]:
            self.stop_reason="evidence_sufficient"
        elif self.idle_steps>=self.limits.max_idle_steps:self.stop_reason="idle_limit"
        return doc
    def receipt(self,*,now:float):
        return {"schema":"skeleton.ai.research.session.v1","session_id":self.session_id,
          "query":self.query.text,"steps":self.steps,"idle_steps":self.idle_steps,
          "stop_reason":self.stop_reason,"crawl_budget":self.engine.budget.__dict__.copy(),
          "assurance":dict(self.evidence.assurance(now=now))}
