"""Identity-preserving governed execution transaction contracts.

This module composes receipts by identity without granting execution authority.
It intentionally has no dependency on candidate PR modules until they land.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

def _digest(prefix,payload):
    return prefix+sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
    return v
def _uint(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be a non-negative integer")
    return v

@dataclass(frozen=True)
class AdmissionBinding:
    authorization_id:str; plan_id:str; resource_lease_id:str; lease_generation:int; expires_at_ns:int
    def __post_init__(self):
        _id(self.authorization_id,"authorization_id");_id(self.plan_id,"plan_id");_id(self.resource_lease_id,"resource_lease_id");_uint(self.lease_generation,"lease_generation");_uint(self.expires_at_ns,"expires_at_ns")

@dataclass(frozen=True)
class PlacementBinding:
    receipt_id:str; snapshot_id:str; topology_generation:int; workload_id:str; resource_lease_id:str; operation_id:str
    def __post_init__(self):
        for n in ("receipt_id","snapshot_id","workload_id","resource_lease_id","operation_id"): _id(getattr(self,n),n)
        _uint(self.topology_generation,"topology_generation")

@dataclass(frozen=True)
class CheckpointBinding:
    checkpoint_id:str; workload_id:str; authorization_id:str; epoch:int; sequence:int; previous_record_id:str|None
    def __post_init__(self):
        for n in ("checkpoint_id","workload_id","authorization_id"): _id(getattr(self,n),n)
        _uint(self.epoch,"epoch");_uint(self.sequence,"sequence")
        if self.previous_record_id is not None: _id(self.previous_record_id,"previous_record_id")

@dataclass(frozen=True)
class ExecutionTransaction:
    transaction_id:str; authorization_id:str; plan_id:str; placement_receipt_id:str; topology_snapshot_id:str; checkpoint_id:str; workload_id:str; operation_id:str; resource_lease_id:str; lease_generation:int; topology_generation:int; recovery_epoch:int; recovery_sequence:int

@dataclass(frozen=True)
class TerminalExecutionReceipt:
    receipt_id:str; transaction_id:str; consumption_record_id:str; outcome:str; evidence_ids:tuple[str,...]

def bind_transaction(admission,placement,checkpoint,now_ns):
    _uint(now_ns,"now_ns")
    if now_ns>=admission.expires_at_ns: raise PermissionError("admission authorization expired")
    if admission.resource_lease_id!=placement.resource_lease_id: raise PermissionError("placement crossed resource lease")
    if admission.authorization_id!=checkpoint.authorization_id: raise PermissionError("checkpoint crossed authorization")
    if placement.workload_id!=checkpoint.workload_id: raise PermissionError("checkpoint crossed workload")
    payload={"authorization_id":admission.authorization_id,"plan_id":admission.plan_id,"placement_receipt_id":placement.receipt_id,"topology_snapshot_id":placement.snapshot_id,"checkpoint_id":checkpoint.checkpoint_id,"workload_id":placement.workload_id,"operation_id":placement.operation_id,"resource_lease_id":admission.resource_lease_id,"lease_generation":admission.lease_generation,"topology_generation":placement.topology_generation,"recovery_epoch":checkpoint.epoch,"recovery_sequence":checkpoint.sequence}
    return ExecutionTransaction(_digest("exec-txn-sha256:",payload),**payload)

def terminal_receipt(transaction,consumption_record_id,outcome,evidence_ids):
    _id(consumption_record_id,"consumption_record_id")
    if outcome not in {"committed","aborted"}: raise ValueError("invalid terminal outcome")
    evidence_ids=tuple(evidence_ids)
    if not evidence_ids or any(not isinstance(x,str) or not x.strip() for x in evidence_ids): raise ValueError("terminal evidence is required")
    if len(set(evidence_ids))!=len(evidence_ids): raise ValueError("duplicate terminal evidence")
    payload={"transaction_id":transaction.transaction_id,"consumption_record_id":consumption_record_id,"outcome":outcome,"evidence_ids":sorted(evidence_ids)}
    return TerminalExecutionReceipt(_digest("exec-terminal-sha256:",payload),transaction.transaction_id,consumption_record_id,outcome,tuple(sorted(evidence_ids)))

def validate_terminal(receipt,transaction,consumption_record_id,outcome,evidence_ids):
    if receipt!=terminal_receipt(transaction,consumption_record_id,outcome,evidence_ids): raise PermissionError("terminal execution receipt identity mismatch")
    return True
