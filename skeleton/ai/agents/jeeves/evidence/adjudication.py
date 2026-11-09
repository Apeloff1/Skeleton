"""Jeeves evidence adjudication: bounded evidence primitives."""
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
class AdjudKind(str,Enum): OBSERVATION="observation"; CLAIM="claim"; COUNTER="counter"; DECISION="decision"; REJECTION="rejection"
@dataclass(frozen=True)
class AdjudEvidence:
    ref:str
    kind:AdjudKind=AdjudKind.OBSERVATION
    text:str=""
    confidence:float=0.0
    metadata:Mapping[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        _text(self.ref);_text(self.text)
        if not 0.0<=self.confidence<=1.0:raise ValueError("confidence")
    @property
    def fingerprint(self)->str:return _digest(self.ref,self.kind.value,self.text,self.confidence,self.metadata)
@dataclass(frozen=True)
class AdjudBundle:
    items:tuple[AdjudEvidence,...]=()
    def add(self,item:AdjudEvidence)->"AdjudBundle":
        if any(x.ref==item.ref for x in self.items):raise ValueError("duplicate evidence ref")
        if len(self.items)>=256:raise ValueError("evidence limit")
        return AdjudBundle(self.items+(item,))
    def digest(self)->str:return _digest(*[x.fingerprint for x in self.items])
@dataclass(frozen=True)
class AdjudCheck000:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck001:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck002:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck003:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck004:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck005:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck006:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck007:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck008:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck009:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck010:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck011:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck012:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck013:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck014:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck015:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck016:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck017:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck018:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck019:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck020:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck021:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck022:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck023:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck024:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck025:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck026:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck027:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck028:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck029:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck030:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck031:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck032:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck033:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck034:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck035:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck036:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck037:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck038:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck039:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck040:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck041:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck042:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck043:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck044:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck045:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck046:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck047:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck048:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck049:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck050:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck051:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck052:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck053:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck054:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck055:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck056:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck057:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck058:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck059:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck060:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck061:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck062:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck063:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck064:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck065:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck066:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck067:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck068:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck069:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck070:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck071:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck072:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck073:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck074:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck075:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck076:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck077:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck078:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck079:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck080:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck081:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck082:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck083:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck084:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck085:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck086:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck087:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck088:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck089:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck090:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck091:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck092:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck093:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck094:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck095:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck096:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck097:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck098:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck099:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck100:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck101:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck102:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck103:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck104:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck105:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck106:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck107:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck108:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck109:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck110:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck111:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck112:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck113:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck114:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck115:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck116:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck117:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck118:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck119:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck120:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck121:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck122:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck123:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck124:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck125:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck126:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck127:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck128:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck129:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck130:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck131:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck132:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck133:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck134:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck135:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck136:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck137:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck138:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck139:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck140:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck141:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck142:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck143:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck144:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck145:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck146:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck147:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck148:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck149:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck150:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck151:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck152:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck153:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck154:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck155:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck156:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck157:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck158:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck159:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck160:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck161:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck162:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck163:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck164:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck165:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck166:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck167:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck168:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck169:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck170:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck171:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck172:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck173:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck174:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck175:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck176:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck177:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck178:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck179:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck180:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck181:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck182:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck183:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck184:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck185:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck186:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck187:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck188:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck189:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck190:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck191:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck192:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck193:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class AdjudCheck194:
    name:str
    required_kind:AdjudKind=AdjudKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:AdjudEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

def validate_adjud(items:Sequence[AdjudEvidence])->tuple[str,...]:
    seen=set();out=[]
    for item in items:
        item.__post_init__()
        if item.ref in seen:raise ValueError("duplicate evidence ref")
        seen.add(item.ref);out.append(item.fingerprint)
    return tuple(out)

def select_adjud(items:Sequence[AdjudEvidence],check:AdjudCheck000)->tuple[AdjudEvidence,...]:
    check.validate();return tuple(x for x in items if check.matches(x))
