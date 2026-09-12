"""Deterministic append-only, hash-chained decision ledger."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import hashlib, json
from typing import Iterable, Mapping, Sequence

class EvidenceKind(str, Enum):
    OBSERVATION="observation"; ASSESSMENT="assessment"; MEMORY="memory"; KNOWLEDGE="knowledge"; REFLECTION="reflection"; TOOL="tool"; MODEL="model"; SYSTEM="system"
class DecisionDisposition(str, Enum):
    PROPOSED="proposed"; ACCEPTED="accepted"; DEFERRED="deferred"; REJECTED="rejected"; SUPERSEDED="superseded"
@dataclass(frozen=True)
class EvidenceRef:
    evidence_id:str; kind:EvidenceKind; subject:str; summary:str; confidence:float=1.; source_id:str=""
    def __post_init__(self):
        if not 0<=self.confidence<=1: raise ValueError("evidence confidence must be in [0, 1]")
@dataclass(frozen=True)
class DecisionRecord:
    sequence:int; decision_id:str; session_id:str; domain:str; action:str; rationale:tuple[str,...]=(); evidence:tuple[str,...]=(); predecessors:tuple[str,...]=(); state_digest:str=""; policy_digest:str=""; disposition:DecisionDisposition=DecisionDisposition.PROPOSED; record_hash:str=""
@dataclass(frozen=True)
class LedgerCheckpoint:
    sequence:int; head_hash:str; record_count:int
@dataclass
class DecisionLedger:
    records:list[DecisionRecord]=field(default_factory=list); evidence:dict[str,EvidenceRef]=field(default_factory=dict); _head_hash:str="GENESIS"
    @property
    def head_hash(self): return self._head_hash
    def register_evidence(self,item):
        old=self.evidence.get(item.evidence_id)
        if old is not None and old!=item: raise ValueError(f"evidence id collision: {item.evidence_id}")
        self.evidence[item.evidence_id]=item
    def append(self,*,session_id,decision_id,domain,action,rationale:Sequence[str]=(),evidence:Sequence[str]=(),predecessors:Sequence[str]=(),state:Mapping[str,object]|None=None,policy:Mapping[str,object]|None=None,disposition=DecisionDisposition.PROPOSED):
        if any(r.decision_id==decision_id for r in self.records): raise ValueError(f"duplicate decision id: {decision_id}")
        missing=tuple(e for e in evidence if e not in self.evidence)
        if missing: raise ValueError(f"unknown evidence references: {missing}")
        missingp=tuple(p for p in predecessors if not any(r.decision_id==p for r in self.records))
        if missingp: raise ValueError(f"unknown predecessor decisions: {missingp}")
        sequence=len(self.records)+1; state_digest=self._digest(state or {}); policy_digest=self._digest(policy or {})
        unsigned={"sequence":sequence,"decision_id":decision_id,"session_id":session_id,"domain":domain,"action":action,"rationale":tuple(rationale),"evidence":tuple(evidence),"predecessors":tuple(predecessors),"state_digest":state_digest,"policy_digest":policy_digest,"disposition":disposition.value,"previous":self._head_hash}; record_hash=self._digest(unsigned)
        record=DecisionRecord(sequence,decision_id,session_id,domain,action,tuple(rationale),tuple(evidence),tuple(predecessors),state_digest,policy_digest,disposition,record_hash); self.records.append(record); self._head_hash=record_hash; return record
    def checkpoint(self): return LedgerCheckpoint(len(self.records),self._head_hash,len(self.records))
    def verify(self):
        previous="GENESIS"
        for expected,r in enumerate(self.records,1):
            if r.sequence!=expected: raise ValueError("decision sequence is not contiguous")
            payload={"sequence":r.sequence,"decision_id":r.decision_id,"session_id":r.session_id,"domain":r.domain,"action":r.action,"rationale":r.rationale,"evidence":r.evidence,"predecessors":r.predecessors,"state_digest":r.state_digest,"policy_digest":r.policy_digest,"disposition":r.disposition.value,"previous":previous}; expected_hash=self._digest(payload)
            if r.record_hash!=expected_hash: raise ValueError(f"decision hash mismatch at sequence {r.sequence}")
            previous=r.record_hash
        if previous!=self._head_hash: raise ValueError("ledger head hash mismatch")
    def session(self,session_id): return tuple(r for r in self.records if r.session_id==session_id)
    def superseded_ids(self) -> frozenset[str]:
        return frozenset(p for r in self.records if r.disposition is DecisionDisposition.SUPERSEDED for p in r.predecessors)
    def active_records(self, session_id: str | None = None) -> tuple[DecisionRecord, ...]:
        records = self.session(session_id) if session_id is not None else tuple(self.records)
        superseded = self.superseded_ids()
        return tuple(r for r in records if r.decision_id not in superseded and r.disposition is not DecisionDisposition.SUPERSEDED)
    def explain(self,decision_id):
        by={r.decision_id:r for r in self.records}
        if decision_id not in by: raise KeyError(decision_id)
        seen=set(); ordered=[]
        def visit(cur):
            if cur in seen:return
            seen.add(cur); r=by[cur]
            for p in r.predecessors:
                if p in by: visit(p)
            ordered.append(r)
        visit(decision_id); return tuple(ordered)
    def supersede(self,decision_id,*,replacement_id):
        if decision_id == replacement_id: raise ValueError("a decision cannot supersede itself")
        if any(r.decision_id == replacement_id for r in self.records): raise ValueError(f"duplicate decision id: {replacement_id}")
        target=next((r for r in self.records if r.decision_id==decision_id),None)
        if target is None: raise KeyError(decision_id)
        if decision_id in self.superseded_ids(): raise ValueError(f"decision already superseded: {decision_id}")
        return self.append(session_id=target.session_id,decision_id=replacement_id,domain=target.domain,action=target.action,rationale=target.rationale+(f"supersedes:{decision_id}",),evidence=target.evidence,predecessors=(decision_id,),disposition=DecisionDisposition.SUPERSEDED)
    @staticmethod
    def _digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def evidence_bundle(items:Iterable[EvidenceRef]):
    result={}
    for item in items:
        if item.evidence_id in result and result[item.evidence_id]!=item: raise ValueError(f"conflicting evidence: {item.evidence_id}")
        result[item.evidence_id]=item
    return tuple(result[k] for k in sorted(result))
