"""Jeeves memory rehydration: bounded memory primitives."""
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
class RehydTier(str,Enum): EPHEMERAL="ephemeral"; WORKING="working"; CANONICAL="canonical"; ARCHIVE="archive"
@dataclass(frozen=True)
class RehydEntry:
    key:str
    value:str
    tier:RehydTier=RehydTier.WORKING
    source:str="runtime"
    metadata:Mapping[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        _text(self.key);_text(self.value);_text(self.source)
    @property
    def fingerprint(self)->str:return _digest(self.key,self.value,self.tier.value,self.source,self.metadata)
@dataclass(frozen=True)
class RehydIndex:
    entries:tuple[RehydEntry,...]=()
    def put(self,entry:RehydEntry)->"RehydIndex":
        if len(self.entries)>=256:raise ValueError("memory limit")
        if any(x.key==entry.key and x.tier is entry.tier for x in self.entries):raise ValueError("duplicate memory key")
        return RehydIndex(self.entries+(entry,))
    def by_tier(self,tier:RehydTier)->tuple[RehydEntry,...]:return tuple(x for x in self.entries if x.tier is tier)
    def digest(self)->str:return _digest(*[x.fingerprint for x in self.entries])
@dataclass(frozen=True)
class RehydPolicy000:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy001:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy002:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy003:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy004:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy005:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy006:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy007:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy008:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy009:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy010:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy011:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy012:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy013:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy014:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy015:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy016:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy017:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy018:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy019:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy020:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy021:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy022:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy023:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy024:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy025:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy026:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy027:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy028:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy029:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy030:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy031:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy032:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy033:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy034:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy035:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy036:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy037:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy038:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy039:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy040:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy041:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy042:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy043:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy044:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy045:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy046:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy047:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy048:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy049:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy050:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy051:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy052:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy053:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy054:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy055:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy056:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy057:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy058:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy059:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy060:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy061:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy062:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy063:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy064:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy065:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy066:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy067:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy068:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy069:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy070:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy071:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy072:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy073:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy074:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy075:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy076:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy077:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy078:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy079:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy080:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy081:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy082:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy083:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy084:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy085:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy086:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy087:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy088:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy089:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy090:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy091:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy092:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy093:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy094:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy095:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy096:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy097:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy098:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy099:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy100:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy101:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy102:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy103:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy104:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy105:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy106:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy107:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy108:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy109:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy110:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy111:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy112:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy113:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy114:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy115:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy116:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy117:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy118:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy119:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy120:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy121:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy122:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy123:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy124:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy125:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy126:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy127:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy128:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy129:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy130:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy131:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy132:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy133:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy134:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy135:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy136:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy137:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy138:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy139:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy140:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy141:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy142:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy143:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy144:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy145:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy146:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy147:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy148:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy149:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy150:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy151:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy152:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy153:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy154:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy155:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy156:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy157:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy158:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy159:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy160:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy161:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy162:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy163:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy164:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy165:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy166:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy167:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy168:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy169:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy170:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy171:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy172:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy173:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy174:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy175:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy176:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy177:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy178:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy179:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy180:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy181:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy182:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy183:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy184:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy185:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy186:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy187:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy188:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy189:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy190:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy191:
    name:str
    tier:RehydTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy192:
    name:str
    tier:RehydTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy193:
    name:str
    tier:RehydTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class RehydPolicy194:
    name:str
    tier:RehydTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:RehydEntry)->bool:
        self.validate();return entry.tier is self.tier

def validate_rehyd(entries:Sequence[RehydEntry])->tuple[str,...]:
    seen=set();out=[]
    for entry in entries:
        entry.__post_init__()
        if (entry.key,entry.tier) in seen:raise ValueError("duplicate memory key")
        seen.add((entry.key,entry.tier));out.append(entry.fingerprint)
    return tuple(out)

def compact_rehyd(entries:Sequence[RehydEntry],tier:RehydTier)->tuple[RehydEntry,...]:
    return tuple(x for x in entries if x.tier is tier)
