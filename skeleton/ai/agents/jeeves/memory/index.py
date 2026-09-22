"""Jeeves memory indexing: bounded memory primitives."""
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
class MemoryTier(str,Enum): EPHEMERAL="ephemeral"; WORKING="working"; CANONICAL="canonical"; ARCHIVE="archive"
@dataclass(frozen=True)
class MemoryEntry:
    key:str
    value:str
    tier:MemoryTier=MemoryTier.WORKING
    source:str="runtime"
    metadata:Mapping[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        _text(self.key);_text(self.value);_text(self.source)
    @property
    def fingerprint(self)->str:return _digest(self.key,self.value,self.tier.value,self.source,self.metadata)
@dataclass(frozen=True)
class MemoryIndex:
    entries:tuple[MemoryEntry,...]=()
    def put(self,entry:MemoryEntry)->"MemoryIndex":
        if len(self.entries)>=256:raise ValueError("memory limit")
        if any(x.key==entry.key and x.tier is entry.tier for x in self.entries):raise ValueError("duplicate memory key")
        return MemoryIndex(self.entries+(entry,))
    def by_tier(self,tier:MemoryTier)->tuple[MemoryEntry,...]:return tuple(x for x in self.entries if x.tier is tier)
    def digest(self)->str:return _digest(*[x.fingerprint for x in self.entries])
@dataclass(frozen=True)
class MemoryPolicy000:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy001:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy002:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy003:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy004:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy005:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy006:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy007:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy008:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy009:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy010:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy011:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy012:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy013:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy014:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy015:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy016:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy017:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy018:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy019:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy020:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy021:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy022:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy023:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy024:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy025:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy026:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy027:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy028:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy029:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy030:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy031:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy032:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy033:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy034:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy035:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy036:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy037:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy038:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy039:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy040:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy041:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy042:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy043:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy044:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy045:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy046:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy047:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy048:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy049:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy050:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy051:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy052:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy053:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy054:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy055:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy056:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy057:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy058:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy059:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy060:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy061:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy062:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy063:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy064:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy065:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy066:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy067:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy068:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy069:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy070:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy071:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy072:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy073:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy074:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy075:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy076:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy077:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy078:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy079:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy080:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy081:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy082:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy083:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy084:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy085:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy086:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy087:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy088:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy089:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy090:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy091:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy092:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy093:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy094:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy095:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy096:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy097:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy098:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy099:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy100:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy101:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy102:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy103:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy104:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy105:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy106:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy107:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy108:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy109:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy110:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy111:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy112:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy113:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy114:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy115:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy116:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy117:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy118:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy119:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy120:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy121:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy122:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy123:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy124:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy125:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy126:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy127:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy128:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy129:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy130:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy131:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy132:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy133:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy134:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy135:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy136:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy137:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy138:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy139:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy140:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy141:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy142:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy143:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy144:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy145:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy146:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy147:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy148:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy149:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy150:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy151:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy152:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy153:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy154:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy155:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy156:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy157:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy158:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy159:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy160:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy161:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy162:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy163:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=4
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy164:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=5
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy165:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=6
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy166:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=7
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy167:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=8
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy168:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=9
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy169:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=10
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy170:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=11
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy171:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=12
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy172:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=13
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy173:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=14
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy174:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=15
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy175:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=16
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy176:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=17
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy177:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=18
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy178:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=19
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy179:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=20
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy180:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=21
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy181:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=22
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy182:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=23
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy183:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=24
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy184:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=25
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy185:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=26
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy186:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=27
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy187:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=28
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy188:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=29
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy189:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=30
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy190:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=31
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy191:
    name:str
    tier:MemoryTier=ARCHIVE
    max_entries:int=32
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy192:
    name:str
    tier:MemoryTier=EPHEMERAL
    max_entries:int=1
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy193:
    name:str
    tier:MemoryTier=WORKING
    max_entries:int=2
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

@dataclass(frozen=True)
class MemoryPolicy194:
    name:str
    tier:MemoryTier=CANONICAL
    max_entries:int=3
    def validate(self)->bool:
        _text(self.name)
        if not 1<=self.max_entries<=256:raise ValueError("max entries")
        return True
    def allows(self,entry:MemoryEntry)->bool:
        self.validate();return entry.tier is self.tier

def validate_memory(entries:Sequence[MemoryEntry])->tuple[str,...]:
    seen=set();out=[]
    for entry in entries:
        entry.__post_init__()
        if (entry.key,entry.tier) in seen:raise ValueError("duplicate memory key")
        seen.add((entry.key,entry.tier));out.append(entry.fingerprint)
    return tuple(out)

def compact_memory(entries:Sequence[MemoryEntry],tier:MemoryTier)->tuple[MemoryEntry,...]:
    return tuple(x for x in entries if x.tier is tier)
