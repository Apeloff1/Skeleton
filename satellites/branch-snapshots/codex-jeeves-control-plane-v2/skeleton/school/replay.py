"""Deterministic replay comparisons for Jeeves decisions."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from typing import Sequence
from skeleton.school.decision_ledger import DecisionRecord
@dataclass(frozen=True)
class ReplayMismatch: sequence:int; expected:str; actual:str; reason:str
@dataclass(frozen=True)
class ReplayReport: session_id:str; matches:int; mismatches:tuple[ReplayMismatch,...]
class JeevesReplay:
 def session(self,records:Sequence[DecisionRecord],session_id:str): return tuple(r for r in records if r.session_id==session_id)
 def compare_actions(self,expected:Sequence[DecisionRecord],actual:Sequence[DecisionRecord]):
  out=[]
  for i,(a,b) in enumerate(zip(expected,actual),1):
   if a.action!=b.action: out.append(ReplayMismatch(i,a.action,b.action,"action divergence"))
  if len(expected)!=len(actual): out.append(ReplayMismatch(min(len(expected),len(actual))+1,str(len(expected)),str(len(actual)),"record count divergence"))
  return ReplayReport(expected[0].session_id if expected else "",max(0,min(len(expected),len(actual))-len(out)),tuple(out))
 def causal_path(self,ledger,decision_id): return ledger.explain(decision_id)
def replay_digest(records:Sequence[DecisionRecord])->str:
 payload=[{"sequence":r.sequence,"decision_id":r.decision_id,"session_id":r.session_id,"action":r.action,"rationale":r.rationale,"evidence":r.evidence,"predecessors":r.predecessors,"state_digest":r.state_digest,"policy_digest":r.policy_digest,"disposition":r.disposition.value,"record_hash":r.record_hash} for r in records]
 return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
