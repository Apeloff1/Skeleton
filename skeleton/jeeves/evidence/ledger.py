"""Jeeves evidence ledger: bounded evidence primitives."""
from __future__ import annotations
from dataclasses import dataclass,field
from enum import Enum
from hashlib import sha256
from typing import Any,Mapping,Sequence
MAX_TEXT=4096

def _text(v:str)->str:
    if not isinstance(v,str) or not v or len(v)>MAX_TEXT or "\x00" in v:raise ValueError("invalid text")
    return v

def _digest(*parts:object)->str:return sha256(repr(parts).encode()).hexdigest()
class LedgerKind(str,Enum): OBSERVATION="observation"; CLAIM="claim"; COUNTER="counter"; DECISION="decision"; REJECTION="rejection"
@dataclass(frozen=True)
class LedgerEvidence:
    ref:str
    kind:LedgerKind=LedgerKind.OBSERVATION
    text:str=""
    confidence:float=0.0
    metadata:Mapping[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        _text(self.ref);_text(self.text)
        if not 0.0<=self.confidence<=1.0:raise ValueError("confidence")
    @property
    def fingerprint(self)->str:return _digest(self.ref,self.kind.value,self.text,self.confidence,self.metadata)
@dataclass(frozen=True)
class LedgerBundle:
    items:tuple[LedgerEvidence,...]=()
    def add(self,item:LedgerEvidence)->"LedgerBundle":
        if any(x.ref==item.ref for x in self.items):raise ValueError("duplicate evidence ref")
        if len(self.items)>=256:raise ValueError("evidence limit")
        return LedgerBundle(self.items+(item,))
    def digest(self)->str:return _digest(*[x.fingerprint for x in self.items])
@dataclass(frozen=True)
class LedgerCheck000:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck001:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck002:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck003:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck004:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck005:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck006:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck007:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck008:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck009:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck010:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck011:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck012:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck013:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck014:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck015:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck016:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck017:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck018:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck019:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck020:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck021:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck022:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck023:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck024:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck025:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck026:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck027:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck028:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck029:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck030:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck031:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck032:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck033:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck034:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck035:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck036:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck037:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck038:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck039:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck040:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck041:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck042:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck043:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck044:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck045:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck046:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck047:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck048:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck049:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck050:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck051:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck052:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck053:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck054:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck055:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck056:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck057:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck058:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck059:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck060:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck061:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck062:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck063:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck064:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck065:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck066:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck067:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck068:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck069:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck070:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck071:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck072:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck073:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck074:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck075:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck076:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck077:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck078:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck079:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck080:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck081:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck082:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck083:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck084:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck085:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck086:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck087:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck088:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck089:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck090:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck091:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck092:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck093:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck094:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck095:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck096:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck097:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck098:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck099:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck100:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck101:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck102:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck103:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck104:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck105:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck106:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck107:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck108:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck109:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck110:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck111:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck112:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck113:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck114:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck115:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck116:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck117:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck118:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck119:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck120:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck121:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck122:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck123:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck124:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck125:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck126:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck127:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck128:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck129:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck130:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck131:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck132:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck133:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck134:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck135:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck136:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck137:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck138:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck139:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck140:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck141:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck142:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck143:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck144:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck145:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck146:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck147:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck148:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck149:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck150:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck151:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck152:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck153:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck154:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck155:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck156:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck157:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck158:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck159:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck160:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck161:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck162:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck163:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck164:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck165:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck166:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck167:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck168:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck169:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck170:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck171:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck172:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck173:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck174:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck175:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck176:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck177:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck178:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck179:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck180:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck181:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck182:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck183:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck184:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck185:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck186:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck187:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck188:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck189:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck190:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck191:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck192:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck193:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class LedgerCheck194:
    name:str
    required_kind:LedgerKind=LedgerKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:LedgerEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

def validate_ledger(items:Sequence[LedgerEvidence])->tuple[str,...]:
    seen=set();out=[]
    for item in items:
        item.__post_init__()
        if item.ref in seen:raise ValueError("duplicate evidence ref")
        seen.add(item.ref);out.append(item.fingerprint)
    return tuple(out)

def select_ledger(items:Sequence[LedgerEvidence],check:LedgerCheck000)->tuple[LedgerEvidence,...]:
    check.validate();return tuple(x for x in items if check.matches(x))
