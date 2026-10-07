from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from typing import Any

MAX_TEXT=4096
MAX_OPTIONS=256

def _text(v:str)->str:
    if not isinstance(v,str) or not v or len(v)>MAX_TEXT or "\x00" in v: raise ValueError("invalid text")
    return v

def digest(v:Any)->str: return sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str).encode()).hexdigest()

class DecisionState(str,Enum):
    DRAFT="draft"; REVIEW="review"; APPROVED="approved"; DEFERRED="deferred"; REJECTED="rejected"; COMMITTED="committed"
class DecisionClass(str,Enum):
    INFORMATIONAL="informational"; OPERATIONAL="operational"; POLICY="policy"; SAFETY="safety"
class ConfidenceBand(str,Enum):
    LOW="low"; MEDIUM="medium"; HIGH="high"

@dataclass(frozen=True,slots=True)
class Criterion:
    name:str; weight:float=1.0; minimum:float=0.0
    def __post_init__(self):
        _text(self.name)
        if not isfinite(self.weight) or self.weight<=0: raise ValueError("invalid criterion weight")
        if not 0<=self.minimum<=1: raise ValueError("invalid criterion minimum")

@dataclass(frozen=True,slots=True)
class Option:
    name:str; rationale:str; values:tuple[tuple[str,float],...]=(); risks:tuple[str,...]=()
    def __post_init__(self):
        _text(self.name); _text(self.rationale)
        if len(self.values)>MAX_OPTIONS or len(self.risks)>MAX_OPTIONS: raise ValueError("option bounds exceeded")
        keys={}
        for k,v in self.values:
            _text(k)
            if not isinstance(v,(int,float)) or isinstance(v,bool) or not isfinite(v) or not 0<=v<=1: raise ValueError("invalid option score")
            if k in keys: raise ValueError("duplicate option metric")
            keys[k]=v
        for risk in self.risks: _text(risk)
    @property
    def id(self)->str: return digest({"name":self.name,"rationale":self.rationale,"values":self.values,"risks":self.risks})

@dataclass(frozen=True,slots=True)
class Decision:
    question:str; classification:DecisionClass; options:tuple[Option,...]; criteria:tuple[Criterion,...]; state:DecisionState=DecisionState.DRAFT; assumptions:tuple[str,...]=()
    def __post_init__(self):
        _text(self.question)
        if not self.options or len(self.options)>MAX_OPTIONS: raise ValueError("invalid option count")
        if not self.criteria or len(self.criteria)>MAX_OPTIONS: raise ValueError("invalid criterion count")
        names=[o.name for o in self.options]
        if len(names)!=len(set(names)): raise ValueError("duplicate option")
        cn=[c.name for c in self.criteria]
        if len(cn)!=len(set(cn)): raise ValueError("duplicate criterion")
        for a in self.assumptions: _text(a)
    @property
    def id(self)->str: return digest(self.to_dict())
    def to_dict(self): return {"question":self.question,"classification":self.classification.value,"options":[{"name":o.name,"rationale":o.rationale,"values":o.values,"risks":o.risks} for o in self.options],"criteria":[{"name":c.name,"weight":c.weight,"minimum":c.minimum} for c in self.criteria],"state":self.state.value,"assumptions":self.assumptions}

def score_option(option:Option,criteria:tuple[Criterion,...])->float:
    values=dict(option.values); total=sum(c.weight for c in criteria)
    if total<=0: raise ValueError("criterion weight total invalid")
    return sum(c.weight*values.get(c.name,0.0) for c in criteria)/total

def confidence(score:float)->ConfidenceBand:
    if not 0<=score<=1: raise ValueError("score out of bounds")
    return ConfidenceBand.HIGH if score>=.8 else ConfidenceBand.MEDIUM if score>=.5 else ConfidenceBand.LOW
