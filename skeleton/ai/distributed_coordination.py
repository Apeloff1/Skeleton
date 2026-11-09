"""Deterministic distributed participant coordination contracts."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _digest(prefix,payload): return prefix+sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
    return v
def _uint(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be a non-negative integer")
    return v

@dataclass(frozen=True)
class Participant:
    participant_id:str; generation:int; role:str; compensation_id:str
    def __post_init__(self):
        _id(self.participant_id,"participant_id");_uint(self.generation,"generation");_id(self.role,"role");_id(self.compensation_id,"compensation_id")

@dataclass(frozen=True)
class ParticipantManifest:
    transaction_id:str; participants:tuple[Participant,...]; policy:str; quorum:int; deadline_ns:int
    def __post_init__(self):
        _id(self.transaction_id,"transaction_id");_uint(self.quorum,"quorum");_uint(self.deadline_ns,"deadline_ns")
        ids=[p.participant_id for p in self.participants]
        if not ids or len(ids)!=len(set(ids)): raise ValueError("participants must be unique and non-empty")
        if self.policy not in {"all","quorum"}: raise ValueError("unsupported prepare policy")
        if self.quorum<1 or self.quorum>len(ids): raise ValueError("invalid quorum")
        if self.policy=="all" and self.quorum!=len(ids): raise ValueError("all policy requires full quorum")
    @property
    def manifest_id(self):
        return _digest("participant-manifest-sha256:",{"transaction_id":self.transaction_id,"policy":self.policy,"quorum":self.quorum,"deadline_ns":self.deadline_ns,"participants":[{"participant_id":p.participant_id,"generation":p.generation,"role":p.role,"compensation_id":p.compensation_id} for p in sorted(self.participants,key=lambda x:x.participant_id)]})

@dataclass(frozen=True)
class PrepareAck:
    ack_id:str; manifest_id:str; transaction_id:str; participant_id:str; generation:int; prepared:bool; evidence_id:str

def acknowledge(manifest,participant_id,generation,prepared,evidence_id,now_ns):
    _id(evidence_id,"evidence_id");_uint(generation,"generation");_uint(now_ns,"now_ns")
    if now_ns>=manifest.deadline_ns: raise TimeoutError("participant acknowledgement deadline expired")
    matches=[p for p in manifest.participants if p.participant_id==participant_id]
    if not matches: raise PermissionError("foreign participant")
    p=matches[0]
    if generation!=p.generation: raise PermissionError("participant generation mismatch")
    if not isinstance(prepared,bool): raise ValueError("prepared must be boolean")
    payload={"manifest_id":manifest.manifest_id,"transaction_id":manifest.transaction_id,"participant_id":participant_id,"generation":generation,"prepared":prepared,"evidence_id":evidence_id}
    return PrepareAck(_digest("prepare-ack-sha256:",payload),manifest.manifest_id,manifest.transaction_id,participant_id,generation,prepared,evidence_id)

@dataclass(frozen=True)
class CoordinationDecision:
    decision_id:str; manifest_id:str; decision:str; prepared_ids:tuple[str,...]; rejected_ids:tuple[str,...]; missing_ids:tuple[str,...]

def decide(manifest,acks,now_ns):
    _uint(now_ns,"now_ns");acks=tuple(acks)
    by_id={}
    for a in acks:
        if a.manifest_id!=manifest.manifest_id or a.transaction_id!=manifest.transaction_id: raise PermissionError("foreign acknowledgement")
        if a.participant_id in by_id: raise ValueError("duplicate participant acknowledgement")
        p=next((p for p in manifest.participants if p.participant_id==a.participant_id),None)
        if p is None or p.generation!=a.generation: raise PermissionError("stale participant acknowledgement")
        by_id[a.participant_id]=a
    prepared=tuple(sorted(x for x,a in by_id.items() if a.prepared))
    rejected=tuple(sorted(x for x,a in by_id.items() if not a.prepared))
    missing=tuple(sorted(p.participant_id for p in manifest.participants if p.participant_id not in by_id))
    enough=len(prepared)>=manifest.quorum
    if rejected and manifest.policy=="all": decision="abort"
    elif enough: decision="commit"
    elif now_ns>=manifest.deadline_ns: decision="abort"
    else: decision="pending"
    payload={"manifest_id":manifest.manifest_id,"decision":decision,"prepared_ids":prepared,"rejected_ids":rejected,"missing_ids":missing}
    return CoordinationDecision(_digest("coordination-decision-sha256:",payload),manifest.manifest_id,decision,prepared,rejected,missing)

def compensation_order(manifest,decision):
    if decision.manifest_id!=manifest.manifest_id or decision.decision!="abort": raise PermissionError("compensation requires matching abort decision")
    by_id={p.participant_id:p for p in manifest.participants}
    return tuple(by_id[x].compensation_id for x in reversed(decision.prepared_ids))
