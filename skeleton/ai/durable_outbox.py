"""Durable-effect outbox contracts with fenced delivery and quarantine."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x): return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be non-negative")

@dataclass(frozen=True)
class OutboxRecord:
    record_id:str; transaction_id:str; effect_key:str; generation:int; payload_digest:str; committed_log_index:int
    @classmethod
    def create(cls,transaction_id,effect_key,generation,payload_digest,committed_log_index):
        for v,n in ((transaction_id,"transaction_id"),(effect_key,"effect_key"),(payload_digest,"payload_digest")):_id(v,n)
        _u(generation,"generation");_u(committed_log_index,"committed_log_index")
        x={"transaction_id":transaction_id,"effect_key":effect_key,"generation":generation,"payload_digest":payload_digest,"committed_log_index":committed_log_index}
        return cls(_h("outbox-sha256:",x),transaction_id,effect_key,generation,payload_digest,committed_log_index)

@dataclass(frozen=True)
class DeliveryLease:
    lease_id:str; record_id:str; generation:int; worker_id:str; attempt:int; issued_at_ns:int; expires_at_ns:int
    @classmethod
    def issue(cls,record,worker_id,attempt,issued_at_ns,expires_at_ns):
        _id(worker_id,"worker_id");_u(attempt,"attempt");_u(issued_at_ns,"issued_at_ns");_u(expires_at_ns,"expires_at_ns")
        if attempt<1 or expires_at_ns<=issued_at_ns: raise ValueError("invalid delivery lease")
        x={"record_id":record.record_id,"generation":record.generation,"worker_id":worker_id,"attempt":attempt,"issued_at_ns":issued_at_ns,"expires_at_ns":expires_at_ns}
        return cls(_h("delivery-lease-sha256:",x),record.record_id,record.generation,worker_id,attempt,issued_at_ns,expires_at_ns)

@dataclass(frozen=True)
class DeliveryAck:
    ack_id:str; record_id:str; lease_id:str; generation:int; outcome:str; evidence_id:str

def acknowledge(record,lease,outcome,evidence_id,now_ns):
    _id(evidence_id,"evidence_id");_u(now_ns,"now_ns")
    if outcome not in {"delivered","failed"}: raise ValueError("invalid delivery outcome")
    if lease.record_id!=record.record_id or lease.generation!=record.generation: raise PermissionError("delivery lease does not match effect generation")
    if now_ns<lease.issued_at_ns or now_ns>=lease.expires_at_ns: raise PermissionError("delivery lease is not live")
    x={"record_id":record.record_id,"lease_id":lease.lease_id,"generation":record.generation,"outcome":outcome,"evidence_id":evidence_id}
    return DeliveryAck(_h("delivery-ack-sha256:",x),record.record_id,lease.lease_id,record.generation,outcome,evidence_id)

@dataclass(frozen=True)
class RetryDecision:
    decision_id:str; record_id:str; next_attempt:int; not_before_ns:int; quarantined:bool; reason:str

def retry_after(record,failed_ack,attempt,now_ns,base_delay_ns,max_attempts):
    _u(attempt,"attempt");_u(now_ns,"now_ns");_u(base_delay_ns,"base_delay_ns");_u(max_attempts,"max_attempts")
    if failed_ack.record_id!=record.record_id or failed_ack.generation!=record.generation or failed_ack.outcome!="failed": raise PermissionError("retry requires matching failed acknowledgement")
    if attempt<1 or max_attempts<1: raise ValueError("attempt bounds must be positive")
    next_attempt=attempt+1;quarantined=next_attempt>max_attempts
    delay=base_delay_ns*(2**min(attempt-1,16))
    not_before=now_ns if quarantined else now_ns+delay
    reason="poison-quarantine" if quarantined else "retry-backoff"
    x={"record_id":record.record_id,"next_attempt":next_attempt,"not_before_ns":not_before,"quarantined":quarantined,"reason":reason}
    return RetryDecision(_h("retry-sha256:",x),record.record_id,next_attempt,not_before,quarantined,reason)

class OutboxLedger:
    def __init__(self,records=()):
        self._by_effect={};self._records=[]
        for r in records:self.add(r)
    def add(self,record):
        if not isinstance(record,OutboxRecord): raise TypeError("invalid outbox record")
        old=self._by_effect.get(record.effect_key)
        if old:
            if old==record:return old
            if record.generation<=old.generation: raise PermissionError("effect generation did not advance")
        self._by_effect[record.effect_key]=record;self._records.append(record);return record
    def pending(self,delivered_record_ids=(),quarantined_record_ids=()):
        done=set(delivered_record_ids)|set(quarantined_record_ids)
        return tuple(r for r in self._records if r.record_id not in done)
    def records(self): return tuple(self._records)
