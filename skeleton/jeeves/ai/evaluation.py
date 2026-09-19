"""Jeeves AI evaluation and evidence plane."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping, Sequence
MAX_TEXT=8192

def _text(v:str)->str:
    if not isinstance(v,str) or not v or len(v)>MAX_TEXT or "\x00" in v: raise ValueError("invalid text")
    return v

def _digest(*parts:object)->str:return sha256("|".join(map(str,parts)).encode()).hexdigest()
class EvalState(str,Enum):
    NEW="new"; READY="ready"; RUNNING="running"; BLOCKED="blocked"; DONE="done"; FAILED="failed"
@dataclass(frozen=True)
class EvalRecord:
    name:str
    state:EvalState=EvalState.NEW
    payload:Mapping[str,Any]=field(default_factory=dict)
    evidence:tuple[str,...]=()
    def __post_init__(self):
        _text(self.name)
        if len(self.evidence)>256:raise ValueError("too much evidence")
    @property
    def digest(self)->str:return _digest(self.name,self.state.value,self.payload,self.evidence)
@dataclass(frozen=True)
class EvalLedger:
    records:tuple[EvalRecord,...]=()
    def append(self,r:EvalRecord)->"EvalLedger":
        if any(x.name==r.name for x in self.records):raise ValueError("duplicate record")
        return EvalLedger(self.records+(r,))
@dataclass(frozen=True)
class EvalContract000:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract001:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract002:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract003:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract004:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract005:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract006:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract007:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract008:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract009:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract010:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract011:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract012:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract013:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract014:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract015:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract016:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract017:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract018:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract019:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract020:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract021:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract022:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract023:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract024:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract025:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract026:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract027:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract028:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract029:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract030:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract031:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract032:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract033:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract034:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract035:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract036:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract037:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract038:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract039:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract040:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract041:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract042:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract043:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract044:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract045:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract046:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract047:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract048:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract049:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract050:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract051:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract052:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract053:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract054:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract055:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract056:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract057:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract058:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract059:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract060:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract061:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract062:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract063:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract064:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract065:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract066:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract067:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract068:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract069:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract070:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract071:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract072:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract073:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract074:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract075:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract076:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract077:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract078:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract079:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract080:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract081:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract082:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract083:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract084:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract085:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract086:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract087:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract088:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract089:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract090:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract091:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract092:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract093:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract094:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract095:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract096:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract097:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract098:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract099:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract100:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract101:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract102:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract103:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract104:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract105:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract106:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract107:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract108:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract109:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract110:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract111:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract112:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract113:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract114:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract115:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract116:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract117:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract118:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract119:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract120:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract121:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract122:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract123:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract124:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract125:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract126:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract127:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract128:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract129:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract130:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract131:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract132:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract133:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract134:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract135:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract136:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract137:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract138:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract139:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract140:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract141:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract142:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract143:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract144:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract145:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract146:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract147:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract148:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract149:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract150:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract151:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract152:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract153:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract154:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract155:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract156:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract157:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract158:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract159:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract160:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract161:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract162:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract163:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract164:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract165:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract166:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract167:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract168:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract169:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract170:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract171:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract172:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract173:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract174:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract175:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract176:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract177:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract178:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract179:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract180:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract181:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract182:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract183:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract184:
    key:str
    value:str
    priority:int=8
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract185:
    key:str
    value:str
    priority:int=9
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract186:
    key:str
    value:str
    priority:int=10
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract187:
    key:str
    value:str
    priority:int=0
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract188:
    key:str
    value:str
    priority:int=1
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract189:
    key:str
    value:str
    priority:int=2
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract190:
    key:str
    value:str
    priority:int=3
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract191:
    key:str
    value:str
    priority:int=4
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract192:
    key:str
    value:str
    priority:int=5
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract193:
    key:str
    value:str
    priority:int=6
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

@dataclass(frozen=True)
class EvalContract194:
    key:str
    value:str
    priority:int=7
    tags:tuple[str,...]=()
    def validate(self)->bool:
        _text(self.key);_text(self.value)
        if not 0<=self.priority<=100:raise ValueError("priority out of range")
        if len(self.tags)>16:raise ValueError("too many tags")
        return True
    def fingerprint(self)->str:
        self.validate()
        return _digest("evaluation and evidence",self.key,self.value,self.priority,self.tags)

def validate_eval(records:Sequence[EvalRecord])->tuple[str,...]:
    seen=set();out=[]
    for r in records:
        r.__post_init__()
        if r.name in seen:raise ValueError("duplicate name")
        seen.add(r.name);out.append(r.digest)
    return tuple(out)

def summarize_eval(records:Sequence[EvalRecord])->Mapping[str,Any]:
    counts={x.value:0 for x in EvalState}
    for r in records:counts[r.state.value]+=1
    return {"count":len(records),"states":counts,"digest":_digest(*[r.digest for r in records])}
