"""Immutable decision lineage graph for VOL-305."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib
from skeleton.contracts.canonical import canonical_json_bytes

class DecisionEdge(str, Enum):
    SUPERSEDES="supersedes"; ACTION="action"; ARTIFACT="artifact"; RESULT="result"

@dataclass(frozen=True)
class DecisionOutcome:
    kind: DecisionEdge
    target_id: str
    summary: str
    def __post_init__(self):
        if not self.target_id or self.target_id.strip()!=self.target_id: raise ValueError("target_id required")
        if not self.summary or self.summary.strip()!=self.summary: raise ValueError("summary required")

@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    decision_digest: str
    outcomes: tuple[DecisionOutcome,...]=()
    supersedes: str|None=None
    correction_reason: str|None=None
    def __post_init__(self):
        if not self.decision_id or self.decision_id.strip()!=self.decision_id: raise ValueError("decision_id required")
        if len(self.decision_digest)!=64 or any(c not in "0123456789abcdef" for c in self.decision_digest): raise ValueError("decision_digest must be sha256")
        if self.supersedes and not self.correction_reason: raise ValueError("supersession requires correction reason")
        if self.supersedes==self.decision_id: raise ValueError("decision cannot supersede itself")
    def payload(self):
        return {"decision_id":self.decision_id,"decision_digest":self.decision_digest,"supersedes":self.supersedes,"correction_reason":self.correction_reason,"outcomes":[{"kind":o.kind.value,"target_id":o.target_id,"summary":o.summary} for o in self.outcomes]}
    @property
    def record_digest(self): return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()

@dataclass(frozen=True)
class DecisionRecordGraph:
    records: tuple[DecisionRecord,...]
    def __post_init__(self):
        ids=[r.decision_id for r in self.records]
        if len(ids)!=len(set(ids)): raise ValueError("decision records are append-only and unique")
        known=set(ids)
        for r in self.records:
            if r.supersedes and r.supersedes not in known: raise ValueError("supersession target missing")
        for start in ids:
            seen=set(); cur=start
            while cur:
                if cur in seen: raise ValueError("supersession cycle")
                seen.add(cur)
                rec=next(x for x in self.records if x.decision_id==cur)
                cur=rec.supersedes
    def append(self, record: DecisionRecord):
        return DecisionRecordGraph(self.records+(record,))
    def impact(self, decision_id: str):
        record=next((r for r in self.records if r.decision_id==decision_id),None)
        if record is None: raise KeyError(decision_id)
        return record.outcomes
