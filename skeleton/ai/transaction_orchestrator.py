"""Crash-safe, authority-neutral execution transaction orchestration."""
from dataclasses import dataclass
from hashlib import sha256
import json

TERMINAL=frozenset({"committed","aborted"})
def _digest(prefix,payload): return prefix+sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
    return v
def _uint(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be a non-negative integer")
    return v

@dataclass(frozen=True)
class OrchestrationIntent:
    transaction_id:str; operation_id:str; deadline_ns:int; compensation_id:str|None; evidence_ids:tuple[str,...]
    def __post_init__(self):
        _id(self.transaction_id,"transaction_id");_id(self.operation_id,"operation_id");_uint(self.deadline_ns,"deadline_ns")
        if self.compensation_id is not None:_id(self.compensation_id,"compensation_id")
        if not self.evidence_ids or any(not isinstance(x,str) or not x.strip() for x in self.evidence_ids): raise ValueError("evidence is required")
        if len(set(self.evidence_ids))!=len(self.evidence_ids): raise ValueError("duplicate evidence")

@dataclass(frozen=True)
class TransitionReceipt:
    receipt_id:str; transaction_id:str; operation_id:str; from_phase:str; to_phase:str; sequence:int; previous_receipt_id:str|None; reason:str; evidence_ids:tuple[str,...]

class TransactionOrchestrator:
    def __init__(self,intent,receipts=()):
        self.intent=intent;self._receipts=[]
        for r in receipts:self._replay(r)

    @property
    def phase(self): return self._receipts[-1].to_phase if self._receipts else "new"
    @property
    def head_id(self): return self._receipts[-1].receipt_id if self._receipts else None
    def receipts(self): return tuple(self._receipts)

    def _replay(self,r):
        if not isinstance(r,TransitionReceipt): raise TypeError("invalid transition receipt")
        if r.transaction_id!=self.intent.transaction_id or r.operation_id!=self.intent.operation_id: raise ValueError("foreign transition receipt")
        expected_seq=len(self._receipts)+1
        if r.sequence!=expected_seq or r.previous_receipt_id!=self.head_id or r.from_phase!=self.phase: raise ValueError("transition chain discontinuity")
        expected=_receipt(self.intent,r.from_phase,r.to_phase,r.sequence,r.previous_receipt_id,r.reason,r.evidence_ids)
        if r!=expected: raise ValueError("transition receipt identity mismatch")
        self._receipts.append(r)

    def transition(self,to_phase,now_ns,reason,evidence_ids=()):
        _uint(now_ns,"now_ns");_id(reason,"reason")
        if self.phase in TERMINAL: raise PermissionError("terminal transaction is immutable")
        allowed={"new":{"prepared","aborted"},"prepared":{"committed","aborted"}}
        if to_phase not in allowed[self.phase]: raise PermissionError("invalid transaction phase transition")
        if now_ns>=self.intent.deadline_ns and to_phase!="aborted": raise PermissionError("transaction deadline expired")
        ev=tuple(sorted(set(self.intent.evidence_ids).union(evidence_ids)))
        if any(not isinstance(x,str) or not x.strip() for x in ev): raise ValueError("invalid transition evidence")
        if to_phase=="aborted" and self.phase=="prepared" and self.intent.compensation_id is None: raise PermissionError("prepared transaction requires compensation identity before abort")
        if self.intent.compensation_id is not None and to_phase=="aborted": ev=tuple(sorted(set(ev+(self.intent.compensation_id,))))
        r=_receipt(self.intent,self.phase,to_phase,len(self._receipts)+1,self.head_id,reason,ev);self._replay(r);return r

def _receipt(intent,from_phase,to_phase,sequence,previous_receipt_id,reason,evidence_ids):
    evidence_ids=tuple(sorted(evidence_ids))
    payload={"transaction_id":intent.transaction_id,"operation_id":intent.operation_id,"from_phase":from_phase,"to_phase":to_phase,"sequence":sequence,"previous_receipt_id":previous_receipt_id,"reason":reason,"evidence_ids":evidence_ids}
    return TransitionReceipt(_digest("txn-transition-sha256:",payload),intent.transaction_id,intent.operation_id,from_phase,to_phase,sequence,previous_receipt_id,reason,evidence_ids)

def recover(intent,receipts): return TransactionOrchestrator(intent,receipts)
