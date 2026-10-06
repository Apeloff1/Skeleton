"""Append-only execution consumption and crash-recovery fencing."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _digest(prefix,payload):
    return prefix+sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _sid(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
    return v
def _uint(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be a non-negative integer")
    return v

@dataclass(frozen=True)
class RecoveryCheckpoint:
    workload_id:str; authorization_id:str; epoch:int; sequence:int; state_digest:str; previous_record_id:str|None
    def __post_init__(self):
        _sid(self.workload_id,"workload_id");_sid(self.authorization_id,"authorization_id");_uint(self.epoch,"epoch");_uint(self.sequence,"sequence");_sid(self.state_digest,"state_digest")
        if self.previous_record_id is not None: _sid(self.previous_record_id,"previous_record_id")
    @property
    def checkpoint_id(self):
        return _digest("checkpoint-sha256:",{"workload_id":self.workload_id,"authorization_id":self.authorization_id,"epoch":self.epoch,"sequence":self.sequence,"state_digest":self.state_digest,"previous_record_id":self.previous_record_id})

@dataclass(frozen=True)
class ConsumptionRecord:
    record_id:str; authorization_id:str; workload_id:str; epoch:int; sequence:int; checkpoint_id:str; previous_record_id:str|None; outcome:str

class ExecutionJournal:
    """Deterministic append-only state machine. Persistence adapters must durably store exported records."""
    def __init__(self,records=()):
        self._records=[]
        self._by_auth={}
        self._head_by_workload={}
        for r in records: self._replay(r)

    def _replay(self,r):
        if not isinstance(r,ConsumptionRecord): raise TypeError("invalid journal record")
        expected=_digest("consume-sha256:",{"authorization_id":r.authorization_id,"workload_id":r.workload_id,"epoch":r.epoch,"sequence":r.sequence,"checkpoint_id":r.checkpoint_id,"previous_record_id":r.previous_record_id,"outcome":r.outcome})
        if r.record_id!=expected: raise ValueError("journal record identity mismatch")
        if r.authorization_id in self._by_auth: raise ValueError("authorization consumed more than once")
        head=self._head_by_workload.get(r.workload_id)
        if r.previous_record_id!=(head.record_id if head else None): raise ValueError("journal chain discontinuity")
        if head and (r.epoch<head.epoch or (r.epoch==head.epoch and r.sequence<=head.sequence)): raise ValueError("journal ordering regression")
        self._records.append(r);self._by_auth[r.authorization_id]=r;self._head_by_workload[r.workload_id]=r

    def consume(self,checkpoint,outcome="committed"):
        if outcome not in {"committed","aborted"}: raise ValueError("invalid terminal outcome")
        if checkpoint.authorization_id in self._by_auth: return self._by_auth[checkpoint.authorization_id]
        head=self._head_by_workload.get(checkpoint.workload_id)
        previous=head.record_id if head else None
        if checkpoint.previous_record_id!=previous: raise PermissionError("stale recovery checkpoint")
        if head and (checkpoint.epoch<head.epoch or (checkpoint.epoch==head.epoch and checkpoint.sequence<=head.sequence)): raise PermissionError("stale recovery epoch or sequence")
        payload={"authorization_id":checkpoint.authorization_id,"workload_id":checkpoint.workload_id,"epoch":checkpoint.epoch,"sequence":checkpoint.sequence,"checkpoint_id":checkpoint.checkpoint_id,"previous_record_id":previous,"outcome":outcome}
        r=ConsumptionRecord(_digest("consume-sha256:",payload),checkpoint.authorization_id,checkpoint.workload_id,checkpoint.epoch,checkpoint.sequence,checkpoint.checkpoint_id,previous,outcome)
        self._replay(r);return r

    def recover(self,records):
        return ExecutionJournal(records)

    def records(self):
        return tuple(self._records)

    def head(self,workload_id):
        return self._head_by_workload.get(workload_id)

    def consumed(self,authorization_id):
        return authorization_id in self._by_auth
