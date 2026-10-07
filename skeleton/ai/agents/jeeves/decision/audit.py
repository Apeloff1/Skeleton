from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from threading import RLock

class AuditKind(str,Enum): CREATED="created"; REVIEWED="reviewed"; GUARDED="guarded"; DEFERRED="deferred"; REJECTED="rejected"
@dataclass(frozen=True,slots=True)
class AuditEvent:
    sequence:int; decision_id:str; kind:AuditKind; detail:str; previous_hash:str; event_hash:str
class DecisionAudit:
    def __init__(self): self._lock=RLock(); self._events=[]; self._keys=set()
    @property
    def events(self):
        with self._lock:return tuple(self._events)
    def append(self,decision_id:str,kind:AuditKind,detail:str)->AuditEvent:
        if len(decision_id)!=64 or not detail or len(detail)>4096: raise ValueError("invalid audit event")
        key=(decision_id,kind,detail)
        with self._lock:
            if key in self._keys: raise ValueError("duplicate audit event")
            prev=self._events[-1].event_hash if self._events else "0"*64; seq=len(self._events)
            p={"sequence":seq,"decision_id":decision_id,"kind":kind.value,"detail":detail,"previous_hash":prev}
            h=sha256(json.dumps(p,sort_keys=True,separators=(",",":")).encode()).hexdigest(); e=AuditEvent(seq,decision_id,kind,detail,prev,h)
            self._events.append(e); self._keys.add(key); return e
    def verify(self):
        with self._lock:
            prev="0"*64
            for i,e in enumerate(self._events):
                p={"sequence":e.sequence,"decision_id":e.decision_id,"kind":e.kind.value,"detail":e.detail,"previous_hash":e.previous_hash}
                if e.sequence!=i or e.previous_hash!=prev or sha256(json.dumps(p,sort_keys=True,separators=(",",":")).encode()).hexdigest()!=e.event_hash:return False
                prev=e.event_hash
            return True
