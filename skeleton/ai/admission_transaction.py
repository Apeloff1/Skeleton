"""Atomic evidence chain for distributed execution admission."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x):return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip():raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0:raise ValueError(f"{n} must be non-negative")

PARTICIPANTS=("schedule","resources","ownership","authorization")

@dataclass(frozen=True)
class AdmissionIntent:
    transaction_id:str; workflow_id:str; step_id:str; generation:int; deadline_ns:int
    @classmethod
    def create(cls,workflow_id,step_id,generation,deadline_ns):
        _id(workflow_id,"workflow_id");_id(step_id,"step_id");_u(generation,"generation");_u(deadline_ns,"deadline_ns")
        x={"workflow_id":workflow_id,"step_id":step_id,"generation":generation,"deadline_ns":deadline_ns}
        return cls(_h("admission-txn-sha256:",x),workflow_id,step_id,generation,deadline_ns)

@dataclass(frozen=True)
class PrepareReceipt:
    receipt_id:str; transaction_id:str; participant:str; generation:int; artifact_id:str; evidence_id:str
    @classmethod
    def create(cls,intent,participant,generation,artifact_id,evidence_id):
        if participant not in PARTICIPANTS:raise ValueError("unknown admission participant")
        _u(generation,"generation");_id(artifact_id,"artifact_id");_id(evidence_id,"evidence_id")
        if generation!=intent.generation:raise PermissionError("participant generation mismatch")
        x={"transaction_id":intent.transaction_id,"participant":participant,"generation":generation,"artifact_id":artifact_id,"evidence_id":evidence_id}
        return cls(_h("admission-prepare-sha256:",x),intent.transaction_id,participant,generation,artifact_id,evidence_id)

@dataclass(frozen=True)
class AdmissionCommit:
    commit_id:str; transaction_id:str; generation:int; prepare_ids:tuple[str,...]; committed_at_ns:int

def commit(intent,prepares,now_ns):
    _u(now_ns,"now_ns")
    if now_ns>=intent.deadline_ns:raise PermissionError("admission deadline expired")
    by={}
    for p in prepares:
        if p.transaction_id!=intent.transaction_id or p.generation!=intent.generation:raise PermissionError("foreign admission preparation")
        if p.participant in by and by[p.participant]!=p:raise PermissionError("conflicting participant preparation")
        by[p.participant]=p
    if set(by)!=set(PARTICIPANTS):raise PermissionError("admission transaction is not fully prepared")
    ids=tuple(by[x].receipt_id for x in PARTICIPANTS)
    x={"transaction_id":intent.transaction_id,"generation":intent.generation,"prepare_ids":ids,"committed_at_ns":now_ns}
    return AdmissionCommit(_h("admission-commit-sha256:",x),intent.transaction_id,intent.generation,ids,now_ns)

@dataclass(frozen=True)
class RollbackReceipt:
    receipt_id:str; transaction_id:str; generation:int; participant:str; prepared_receipt_id:str; reason:str; evidence_id:str

def rollback(intent,prepares,reason,evidence_id):
    _id(reason,"reason");_id(evidence_id,"evidence_id")
    unique={}
    for p in prepares:
        if p.transaction_id!=intent.transaction_id or p.generation!=intent.generation:raise PermissionError("foreign admission preparation")
        if p.participant in unique and unique[p.participant]!=p:raise PermissionError("conflicting participant preparation")
        unique[p.participant]=p
    out=[]
    for participant in reversed(PARTICIPANTS):
        p=unique.get(participant)
        if p is None:continue
        x={"transaction_id":intent.transaction_id,"generation":intent.generation,"participant":participant,"prepared_receipt_id":p.receipt_id,"reason":reason,"evidence_id":evidence_id}
        out.append(RollbackReceipt(_h("admission-rollback-sha256:",x),intent.transaction_id,intent.generation,participant,p.receipt_id,reason,evidence_id))
    return tuple(out)

@dataclass(frozen=True)
class RecoveryDecision:
    decision_id:str; transaction_id:str; action:str; evidence_ids:tuple[str,...]

def recover(intent,prepares,commit_receipt,rollback_receipts,now_ns):
    _u(now_ns,"now_ns")
    if commit_receipt is not None:
        expected=commit(intent,prepares,commit_receipt.committed_at_ns)
        if expected!=commit_receipt:raise PermissionError("invalid admission commit evidence")
        action="committed";ids=(commit_receipt.commit_id,)
    elif rollback_receipts:
        expected=rollback(intent,prepares,rollback_receipts[0].reason,rollback_receipts[0].evidence_id)
        if tuple(rollback_receipts)!=expected:raise PermissionError("incomplete or forged rollback evidence")
        action="rolled-back";ids=tuple(r.receipt_id for r in expected)
    elif now_ns>=intent.deadline_ns:
        action="rollback-required";ids=tuple(sorted(p.receipt_id for p in prepares))
    else:
        action="resume-prepare";ids=tuple(sorted(p.receipt_id for p in prepares))
    x={"transaction_id":intent.transaction_id,"action":action,"evidence_ids":ids}
    return RecoveryDecision(_h("admission-recovery-sha256:",x),intent.transaction_id,action,ids)
