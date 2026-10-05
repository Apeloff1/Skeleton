"""Executable runbook contracts for VOL-091."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib, json, re
from typing import Iterable

_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA=re.compile(r"^[0-9a-f]{64}$")


class RunbookError(ValueError): pass
class StepKind(str,Enum):
    OBSERVE="observe"; COMMAND="command"; DECISION="decision"; ROLLBACK="rollback"; ESCALATE="escalate"; STOP="stop"
class ValidationStatus(str,Enum):
    PASSED="passed"; FAILED="failed"


def _id(v,f):
    if not isinstance(v,str) or not _ID.fullmatch(v): raise RunbookError(f"{f} must be stable identifier")
    return v
def _text(v,f):
    if not isinstance(v,str) or not v.strip() or "\x00" in v: raise RunbookError(f"{f} must be non-empty safe text")
    return v.strip()
def _digest(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True,slots=True)
class RunbookStep:
    step_id:str; kind:StepKind; instruction:str
    signal_ref:str|None=None; command_ref:str|None=None; authority_ref:str|None=None
    rollback_step_id:str|None=None; next_step_ids:tuple[str,...]=()
    def __post_init__(self):
        object.__setattr__(self,"step_id",_id(self.step_id,"step_id"))
        object.__setattr__(self,"instruction",_text(self.instruction,"instruction"))
        for f in ("signal_ref","command_ref","authority_ref","rollback_step_id"):
            v=getattr(self,f)
            if v is not None: object.__setattr__(self,f,_id(v,f))
        ns=tuple(sorted(set(self.next_step_ids)))
        for n in ns:_id(n,"next_step_id")
        object.__setattr__(self,"next_step_ids",ns)
        if self.kind is StepKind.OBSERVE and self.signal_ref is None: raise RunbookError("observe step requires signal_ref")
        if self.kind is StepKind.COMMAND and (self.command_ref is None or self.authority_ref is None): raise RunbookError("command step requires command_ref and authority_ref")
        if self.kind is StepKind.ROLLBACK and self.command_ref is None: raise RunbookError("rollback step requires command_ref")
        if self.kind in (StepKind.ESCALATE,StepKind.STOP) and self.next_step_ids: raise RunbookError("terminal step cannot have successors")
    @property
    def digest(self): return _digest({"step_id":self.step_id,"kind":self.kind.value,"instruction":self.instruction,"signal_ref":self.signal_ref,"command_ref":self.command_ref,"authority_ref":self.authority_ref,"rollback_step_id":self.rollback_step_id,"next_step_ids":self.next_step_ids})


@dataclass(frozen=True,slots=True)
class Runbook:
    runbook_id:str; version:str; owner:str; degraded_mode:str
    entry_step_id:str; steps:tuple[RunbookStep,...]
    def __post_init__(self):
        object.__setattr__(self,"runbook_id",_id(self.runbook_id,"runbook_id")); object.__setattr__(self,"version",_id(self.version,"version")); object.__setattr__(self,"owner",_text(self.owner,"owner")); object.__setattr__(self,"degraded_mode",_text(self.degraded_mode,"degraded_mode")); object.__setattr__(self,"entry_step_id",_id(self.entry_step_id,"entry_step_id"))
        steps=tuple(sorted(self.steps,key=lambda s:s.step_id)); ids={s.step_id for s in steps}
        if len(ids)!=len(steps): raise RunbookError("duplicate step identity")
        if self.entry_step_id not in ids: raise RunbookError("entry step is missing")
        for s in steps:
            if any(n not in ids for n in s.next_step_ids): raise RunbookError("step references unknown successor")
            if s.rollback_step_id and s.rollback_step_id not in ids: raise RunbookError("step references unknown rollback")
            if s.rollback_step_id and next(x for x in steps if x.step_id==s.rollback_step_id).kind is not StepKind.ROLLBACK: raise RunbookError("rollback target must be rollback step")
        reachable=set(); stack=[self.entry_step_id]
        by={s.step_id:s for s in steps}
        while stack:
            cur=stack.pop()
            if cur in reachable: continue
            reachable.add(cur); stack.extend(by[cur].next_step_ids)
        if reachable!=ids: raise RunbookError("runbook contains unreachable steps")
        if not any(s.kind in (StepKind.STOP,StepKind.ESCALATE) for s in steps): raise RunbookError("runbook requires explicit stop or escalation")
        object.__setattr__(self,"steps",steps)
    @property
    def digest(self): return _digest({"runbook_id":self.runbook_id,"version":self.version,"owner":self.owner,"degraded_mode":self.degraded_mode,"entry_step_id":self.entry_step_id,"steps":[s.digest for s in self.steps]})


@dataclass(frozen=True,slots=True)
class RunbookValidation:
    validation_id:str; runbook_id:str; runbook_digest:str; drill_id:str; status:ValidationStatus; evidence_digest:str
    def __post_init__(self):
        for f in ("validation_id","runbook_id","drill_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
        for f in ("runbook_digest","evidence_digest"):
            if not isinstance(getattr(self,f),str) or not _SHA.fullmatch(getattr(self,f)):raise RunbookError(f"{f} must be lowercase sha256")


class RunbookRegistry:
    def __init__(self): self._books={}; self._validations={}
    def register(self,book:Runbook):
        key=(book.runbook_id,book.version); prior=self._books.get(key)
        if prior is not None and prior!=book: raise RunbookError("runbook version is immutable")
        self._books[key]=book
    def record_validation(self,item:RunbookValidation):
        matches=[b for b in self._books.values() if b.runbook_id==item.runbook_id and b.digest==item.runbook_digest]
        if not matches: raise RunbookError("validation is not bound to a registered exact runbook")
        prior=self._validations.get(item.validation_id)
        if prior is not None and prior!=item: raise RunbookError("validation identity is immutable")
        self._validations[item.validation_id]=item
    def validated(self,runbook_id:str,version:str)->bool:
        book=self._books.get((runbook_id,version))
        if book is None: raise RunbookError("unknown runbook version")
        return any(v.runbook_digest==book.digest and v.status is ValidationStatus.PASSED for v in self._validations.values())
