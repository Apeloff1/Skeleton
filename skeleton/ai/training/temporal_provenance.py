"""Detect provenance echoes so copied sources do not fake corroboration."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class ProvenanceNode:
 source_digest:str; parent_source_digests:tuple[str,...]=()
 def __post_init__(self):
  _hex(self.source_digest,"source")
  for x in self.parent_source_digests: _hex(x,"parent source")
  if self.source_digest in self.parent_source_digests: raise TemporalSignalError("self-dependent source")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class IndependenceReceipt:
 source_digests:tuple[str,...]; root_digests:tuple[str,...]; independent_root_count:int; echo_count:int
 @property
 def digest(self): return _digest(self.__dict__)

def assess_source_independence(nodes):
 nodes=tuple(nodes); by={n.source_digest:n for n in nodes}
 if len(by)!=len(nodes): raise TemporalSignalError("duplicate provenance source")
 visiting=set(); memo={}
 def roots(d):
  if d in memo:return memo[d]
  if d in visiting: raise TemporalSignalError("provenance dependency cycle")
  visiting.add(d); n=by[d]
  r={d} if not n.parent_source_digests else set().union(*(roots(p) if p in by else {p} for p in n.parent_source_digests))
  visiting.remove(d); memo[d]=r; return r
 all_roots=set(); echoes=0
 seen=set()
 for n in nodes:
  r=frozenset(roots(n.source_digest)); all_roots|=r
  if r & seen: echoes+=1
  seen|=r
 return IndependenceReceipt(tuple(sorted(by)),tuple(sorted(all_roots)),len(all_roots),echoes)

def require_independent_roots(receipt,*,minimum=2):
 if receipt.independent_root_count<minimum: raise TemporalSignalError("insufficient independent provenance roots")
 return receipt.digest

__all__=["ProvenanceNode","IndependenceReceipt","assess_source_independence","require_independent_roots"]
