"""Causal chronology authority: precedence is not causation."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalEvent:
 event_id:str; subject:str; year:int; evidence_digest:str
 def __post_init__(self): _hex(self.evidence_digest,"event evidence")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class CausalEdge:
 edge_id:str; cause_event_digest:str; effect_event_digest:str; relation:str; evidence_digest:str
 def __post_init__(self):
  if self.relation not in {"causal","enabling","correlational","precedence-only"}: raise TemporalSignalError("invalid causal relation")
  for n in ("cause_event_digest","effect_event_digest","evidence_digest"): _hex(getattr(self,n),n)
  if self.cause_event_digest==self.effect_event_digest: raise TemporalSignalError("self causal edge")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class CausalChronologyReceipt:
 event_digests:tuple[str,...]; edge_digests:tuple[str,...]; causal_edge_count:int; precedence_only_count:int; acyclic:bool
 @property
 def digest(self): return _digest(self.__dict__)

def validate_causal_chronology(events,edges):
 events=tuple(events); edges=tuple(edges); by={e.digest:e for e in events}
 if len(by)!=len(events): raise TemporalSignalError("duplicate temporal event")
 graph={d:[] for d in by}
 for edge in edges:
  if edge.cause_event_digest not in by or edge.effect_event_digest not in by: raise TemporalSignalError("causal edge references unknown event")
  a=by[edge.cause_event_digest]; b=by[edge.effect_event_digest]
  if a.year>b.year: raise TemporalSignalError("cause occurs after effect")
  graph[a.digest].append(b.digest)
 visiting=set(); done=set()
 def visit(n):
  if n in visiting: raise TemporalSignalError("causal chronology cycle")
  if n in done:return
  visiting.add(n)
  for x in graph[n]:visit(x)
  visiting.remove(n);done.add(n)
 for n in graph:visit(n)
 return CausalChronologyReceipt(tuple(sorted(by)),tuple(sorted(e.digest for e in edges)),sum(e.relation in {"causal","enabling"} for e in edges),sum(e.relation=="precedence-only" for e in edges),True)

__all__=["TemporalEvent","CausalEdge","CausalChronologyReceipt","validate_causal_chronology"]
