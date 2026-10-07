"""Jeeves provenance tracking: bounded evidence primitives."""
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
class ProvKind(str,Enum): OBSERVATION="observation"; CLAIM="claim"; COUNTER="counter"; DECISION="decision"; REJECTION="rejection"
@dataclass(frozen=True)
class ProvEvidence:
    ref:str
    kind:ProvKind=ProvKind.OBSERVATION
    text:str=""
    confidence:float=0.0
    metadata:Mapping[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        _text(self.ref);_text(self.text)
        if not 0.0<=self.confidence<=1.0:raise ValueError("confidence")
    @property
    def fingerprint(self)->str:return _digest(self.ref,self.kind.value,self.text,self.confidence,self.metadata)
@dataclass(frozen=True)
class ProvBundle:
    items:tuple[ProvEvidence,...]=()
    def add(self,item:ProvEvidence)->"ProvBundle":
        if any(x.ref==item.ref for x in self.items):raise ValueError("duplicate evidence ref")
        if len(self.items)>=256:raise ValueError("evidence limit")
        return ProvBundle(self.items+(item,))
    def digest(self)->str:return _digest(*[x.fingerprint for x in self.items])
@dataclass(frozen=True)
class ProvCheck000:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck001:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck002:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck003:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck004:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck005:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck006:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck007:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck008:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck009:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck010:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck011:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck012:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck013:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck014:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck015:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck016:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck017:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck018:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck019:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck020:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck021:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck022:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck023:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck024:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck025:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck026:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck027:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck028:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck029:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck030:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck031:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck032:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck033:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck034:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck035:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck036:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck037:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck038:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck039:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck040:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck041:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck042:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck043:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck044:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck045:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck046:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck047:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck048:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck049:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck050:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck051:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck052:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck053:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck054:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck055:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck056:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck057:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck058:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck059:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck060:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck061:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck062:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck063:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck064:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck065:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck066:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck067:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck068:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck069:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck070:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck071:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck072:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck073:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck074:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck075:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck076:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck077:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck078:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck079:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck080:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck081:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck082:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck083:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck084:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck085:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck086:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck087:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck088:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck089:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck090:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck091:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck092:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck093:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck094:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck095:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck096:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck097:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck098:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck099:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck100:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck101:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck102:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck103:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck104:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck105:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck106:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck107:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck108:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck109:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck110:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck111:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck112:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck113:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck114:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck115:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck116:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck117:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck118:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck119:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck120:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck121:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck122:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck123:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck124:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck125:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck126:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck127:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck128:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck129:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck130:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck131:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck132:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck133:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck134:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck135:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck136:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck137:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck138:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck139:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck140:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck141:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck142:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck143:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck144:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck145:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck146:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck147:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck148:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck149:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck150:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck151:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck152:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck153:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck154:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck155:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck156:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck157:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck158:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck159:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck160:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck161:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck162:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck163:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck164:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck165:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck166:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck167:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck168:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck169:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck170:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck171:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck172:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck173:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck174:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck175:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck176:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck177:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck178:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck179:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck180:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck181:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck182:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck183:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck184:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck185:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.5
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck186:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.6
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck187:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.7
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck188:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.8
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck189:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.9
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck190:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck191:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.1
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck192:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.2
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck193:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.3
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

@dataclass(frozen=True)
class ProvCheck194:
    name:str
    required_kind:ProvKind=ProvKind.OBSERVATION
    minimum_confidence:float=0.4
    def validate(self)->bool:
        _text(self.name)
        if not 0.0<=self.minimum_confidence<=1.0:raise ValueError("minimum confidence")
        return True
    def matches(self,item:ProvEvidence)->bool:
        self.validate()
        return item.kind is self.required_kind and item.confidence>=self.minimum_confidence

def validate_prov(items:Sequence[ProvEvidence])->tuple[str,...]:
    seen=set();out=[]
    for item in items:
        item.__post_init__()
        if item.ref in seen:raise ValueError("duplicate evidence ref")
        seen.add(item.ref);out.append(item.fingerprint)
    return tuple(out)

def select_prov(items:Sequence[ProvEvidence],check:ProvCheck000)->tuple[ProvEvidence,...]:
    check.validate();return tuple(x for x in items if check.matches(x))
