"""Jeeves AI evaluation and evidence plane. Declarative, deterministic control primitives."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping, Sequence
MAX_TEXT=8192
MAX_ITEMS=256
def _text(v: str) -> str:
    if not isinstance(v,str) or not v or len(v)>MAX_TEXT or "\x00" in v: raise ValueError("invalid text")
    return v
def _digest(*parts: object) -> str: return sha256("|".join(str(p) for p in parts).encode()).hexdigest()
class EvalState(str, Enum):
    NEW="new"; READY="ready"; RUNNING="running"; BLOCKED="blocked"; DONE="done"; FAILED="failed"
@dataclass(frozen=True)
class EvalRecord:
    name: str
    state: EvalState=EvalState.NEW
    payload: Mapping[str,Any]=field(default_factory=dict)
    evidence: tuple[str,...]=()
    def __post_init__(self):
        _text(self.name)
        if len(self.evidence)>MAX_ITEMS: raise ValueError("too much evidence")
    @property
    def digest(self)->str: return _digest(self.name,self.state.value,sorted(self.payload.items()),self.evidence)
@dataclass(frozen=True)
class EvalLedger:
    records: tuple[EvalRecord,...]=()
    def append(self, record:EvalRecord)->"EvalLedger":
        if any(r.name==record.name for r in self.records): raise ValueError("duplicate record")
        return EvalLedger(self.records+(record,))
    def latest(self)->EvalRecord|None: return self.records[-1] if self.records else None
@dataclass(frozen=True)
class EvalContract0000:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0001:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0002:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0003:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0004:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0005:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0006:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0007:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0008:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0009:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0010:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0011:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0012:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0013:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0014:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0015:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0016:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0017:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0018:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0019:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0020:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0021:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0022:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0023:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0024:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0025:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0026:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0027:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0028:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0029:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0030:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0031:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0032:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0033:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0034:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0035:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0036:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0037:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0038:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0039:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0040:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0041:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0042:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0043:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0044:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0045:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0046:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0047:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0048:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0049:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0050:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0051:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0052:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0053:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0054:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0055:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0056:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0057:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0058:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0059:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0060:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0061:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0062:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0063:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0064:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0065:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0066:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0067:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0068:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0069:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0070:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0071:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0072:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0073:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0074:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0075:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0076:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0077:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0078:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0079:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0080:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0081:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0082:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0083:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0084:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0085:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0086:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0087:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0088:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0089:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0090:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0091:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0092:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0093:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0094:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0095:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0096:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0097:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0098:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0099:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0100:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0101:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0102:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0103:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0104:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0105:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0106:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0107:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0108:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0109:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0110:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0111:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0112:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0113:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0114:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0115:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0116:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0117:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0118:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0119:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0120:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0121:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0122:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0123:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0124:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0125:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0126:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0127:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0128:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0129:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0130:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0131:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0132:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0133:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0134:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0135:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0136:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0137:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0138:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0139:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0140:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0141:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0142:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0143:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0144:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0145:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0146:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0147:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0148:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0149:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0150:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0151:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0152:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0153:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0154:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0155:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0156:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0157:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0158:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0159:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0160:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0161:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0162:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0163:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0164:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0165:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0166:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0167:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0168:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0169:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0170:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0171:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0172:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0173:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0174:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0175:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0176:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0177:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0178:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0179:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0180:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0181:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0182:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0183:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0184:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0185:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0186:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0187:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0188:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0189:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0190:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0191:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0192:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0193:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0194:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0195:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0196:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0197:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0198:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0199:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0200:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0201:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0202:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0203:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0204:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0205:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0206:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0207:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0208:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0209:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0210:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0211:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0212:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0213:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0214:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0215:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0216:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0217:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0218:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0219:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0220:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0221:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0222:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0223:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0224:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0225:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0226:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0227:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0228:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0229:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0230:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0231:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0232:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0233:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0234:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0235:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0236:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0237:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0238:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0239:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0240:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0241:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0242:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0243:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0244:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0245:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0246:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0247:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0248:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0249:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0250:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0251:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0252:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0253:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0254:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0255:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0256:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0257:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0258:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0259:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0260:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0261:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0262:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0263:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0264:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0265:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0266:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0267:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0268:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0269:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0270:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0271:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0272:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0273:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0274:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0275:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0276:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0277:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0278:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0279:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0280:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0281:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0282:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0283:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0284:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0285:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0286:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0287:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0288:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0289:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0290:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0291:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0292:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0293:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0294:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0295:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0296:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0297:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0298:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0299:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0300:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0301:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0302:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0303:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0304:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0305:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0306:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0307:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0308:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0309:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0310:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0311:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0312:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0313:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0314:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0315:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0316:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0317:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0318:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0319:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0320:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0321:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0322:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0323:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0324:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0325:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0326:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0327:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0328:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0329:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0330:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0331:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0332:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0333:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0334:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0335:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0336:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0337:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0338:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0339:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0340:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0341:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0342:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0343:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0344:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0345:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0346:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0347:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0348:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0349:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0350:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0351:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0352:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0353:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0354:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0355:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0356:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0357:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0358:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0359:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0360:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0361:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0362:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0363:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0364:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0365:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0366:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0367:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0368:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0369:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0370:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0371:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0372:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0373:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0374:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0375:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0376:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0377:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0378:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0379:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0380:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0381:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0382:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0383:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0384:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0385:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0386:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0387:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0388:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0389:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0390:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0391:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0392:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0393:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0394:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0395:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0396:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0397:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0398:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0399:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0400:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0401:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0402:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0403:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0404:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0405:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0406:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0407:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0408:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0409:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0410:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0411:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0412:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0413:
    key: str
    value: str
    priority: int = 0
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0414:
    key: str
    value: str
    priority: int = 1
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0415:
    key: str
    value: str
    priority: int = 2
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0416:
    key: str
    value: str
    priority: int = 3
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0417:
    key: str
    value: str
    priority: int = 4
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0418:
    key: str
    value: str
    priority: int = 5
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

@dataclass(frozen=True)
class EvalContract0419:
    key: str
    value: str
    priority: int = 6
    tags: tuple[str,...] = ()
    def validate(self) -> bool:
        _text(self.key); _text(self.value)
        if self.priority < 0 or self.priority > 100: raise ValueError("priority out of range")
        if len(self.tags) > 16: raise ValueError("too many tags")
        return True
    def fingerprint(self) -> str:
        self.validate()
        return _digest("evaluation and evidence", self.key, self.value, self.priority, self.tags)

def validate_eval_plane(records: Sequence[EvalRecord]) -> tuple[str,...]:
    names=set(); out=[]
    for r in records:
        r.__post_init__()
        if r.name in names: raise ValueError("duplicate name")
        names.add(r.name); out.append(r.digest)
    return tuple(out)
def summarize_eval_plane(records: Sequence[EvalRecord]) -> Mapping[str,Any]:
    states={state.value:0 for state in EvalState}
    for r in records: states[r.state.value]+=1
    return {"count":len(records),"states":states,"digest":_digest(*[r.digest for r in records])}
