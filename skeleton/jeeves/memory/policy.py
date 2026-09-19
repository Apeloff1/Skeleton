"""Jeeves memory policy: bounded memory primitives."""
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
class MemPolicyTier(str,Enum): EPHEMERAL="ephemeral"; WORKING="working"; CANONICAL="canonical"; ARCHIVE="archive"
@dataclass(frozen=True)
class MemPolicyEntry:
    key:str
    value:str
    tier:MemPolicyTier=MemPolicyTier.WORKING
    source:str="runtime"
    metadata:Mapping[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        _text(self.key);_text(self.value);_text(self.source)
    @property
    def fingerprint(self)->str:return _digest(self.key,self.value,self.tier.value,self.source,self.metadata)
@dataclass(frozen=True)
class MemPolicyIndex:
    entries:tuple[MemPolicyEntry,...]=()
    def put(self,entry:MemPolicyEntry)->"MemPolicyIndex":
        if len(self.entries)>=256:raise ValueError("memory limit")
        if any(x.key==entry.key and x.tier is entry.tier for x in self.entries):raise ValueError("duplicate memory key")
        return MemPolicyIndex(self.entries+(entry,))
    def by_tier(self,tier:MemPolicyTier)->tuple[MemPolicyEntry,...]:return tuple(x for x in self.entries if x.tier is tier)
    def digest(self)->str:return _digest(*[x.fingerprint for x in self.entries])
@dataclass(frozen=True)
class MemPolicyPolicy000:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy001:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy002:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy003:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy004:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy005:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy006:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy007:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy008:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy009:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy010:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy011:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy012:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy013:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy014:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy015:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy016:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy017:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy018:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy019:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy020:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy021:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy022:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy023:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy024:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy025:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy026:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy027:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy028:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy029:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy030:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy031:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy032:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy033:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy034:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy035:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy036:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy037:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy038:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy039:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy040:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy041:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy042:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy043:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy044:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy045:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy046:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy047:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy048:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy049:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy050:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy051:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy052:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy053:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy054:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy055:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy056:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy057:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy058:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy059:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy060:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy061:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy062:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy063:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy064:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy065:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy066:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy067:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy068:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy069:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy070:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy071:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy072:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy073:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy074:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy075:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy076:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy077:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy078:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy079:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy080:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy081:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy082:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy083:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy084:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy085:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy086:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy087:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy088:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy089:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy090:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy091:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy092:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy093:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy094:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy095:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy096:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy097:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy098:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy099:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy100:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy101:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy102:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy103:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy104:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy105:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy106:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy107:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy108:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy109:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy110:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy111:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy112:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy113:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy114:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy115:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy116:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy117:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy118:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy119:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy120:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy121:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy122:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy123:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy124:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy125:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy126:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy127:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy128:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy129:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy130:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy131:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy132:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy133:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy134:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy135:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy136:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy137:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy138:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy139:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy140:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy141:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy142:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy143:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy144:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy145:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy146:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy147:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy148:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy149:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy150:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy151:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy152:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy153:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy154:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy155:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy156:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy157:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy158:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy159:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy160:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy161:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy162:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy163:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy164:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy165:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy166:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy167:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy168:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy169:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy170:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy171:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy172:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy173:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy174:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy175:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy176:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy177:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy178:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy179:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy180:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy181:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy182:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy183:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy184:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy185:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy186:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy187:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy188:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy189:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy190:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy191:
    name:str
    tier:MemPolicyTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy192:
    name:str
    tier:MemPolicyTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy193:
    name:str
    tier:MemPolicyTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemPolicyPolicy194:
    name:str
    tier:MemPolicyTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemPolicyEntry)->bool:
        self.validate();return entry.tier is self.tier

def validate_mempolicy(entries:Sequence[MemPolicyEntry])->tuple[str,...]:
    seen=set();out=[]
    for entry in entries:
        entry.__post_init__()
        if (entry.key,entry.tier) in seen:raise ValueError("duplicate memory key")
        seen.add((entry.key,entry.tier));out.append(entry.fingerprint)
    return tuple(out)

def compact_mempolicy(entries:Sequence[MemPolicyEntry],tier:MemPolicyTier)->tuple[MemPolicyEntry,...]:
    return tuple(x for x in entries if x.tier is tier)
