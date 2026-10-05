"""Typed master traceability graph for VOL-112."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class TraceError(ValueError):pass
class NodeKind(str,Enum): REQUIREMENT="requirement"; IMPLEMENTATION="implementation"; TEST="test"; EVIDENCE="evidence"
class EdgeKind(str,Enum): IMPLEMENTS="implements"; VERIFIES="verifies"; EVIDENCES="evidences"; DEPENDS_ON="depends_on"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise TraceError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class TraceNode:
 node_id:str;kind:NodeKind;locator:str
 def __post_init__(self):
  object.__setattr__(self,"node_id",_id(self.node_id,"node_id"))
  if not self.locator.strip():raise TraceError("node locator required")
@dataclass(frozen=True,slots=True)
class TraceEdge:
 source_id:str;target_id:str;kind:EdgeKind
 def __post_init__(self):
  object.__setattr__(self,"source_id",_id(self.source_id,"source_id"));object.__setattr__(self,"target_id",_id(self.target_id,"target_id"))
  if self.source_id==self.target_id:raise TraceError("self trace edge")
class TraceabilityMatrix:
 def __init__(self,nodes,edges):
  self.nodes={n.node_id:n for n in nodes}
  if len(self.nodes)!=len(tuple(nodes)):raise TraceError("duplicate trace node")
  self.edges=tuple(edges)
  for e in self.edges:
   if e.source_id not in self.nodes or e.target_id not in self.nodes:raise TraceError("dangling trace edge")
   self._validate_edge(e)
 def _validate_edge(self,e):
  a,b=self.nodes[e.source_id],self.nodes[e.target_id]
  allowed={
   EdgeKind.IMPLEMENTS:(NodeKind.IMPLEMENTATION,NodeKind.REQUIREMENT),
   EdgeKind.VERIFIES:(NodeKind.TEST,NodeKind.IMPLEMENTATION),
   EdgeKind.EVIDENCES:(NodeKind.EVIDENCE,NodeKind.TEST),
  }
  if e.kind in allowed and (a.kind,b.kind)!=allowed[e.kind]:raise TraceError("contradictory trace edge types")
 def orphan_requirements(self):
  targets={e.target_id for e in self.edges if e.kind is EdgeKind.IMPLEMENTS}
  return tuple(sorted(n.node_id for n in self.nodes.values() if n.kind is NodeKind.REQUIREMENT and n.node_id not in targets))
 def impact(self,start_id):
  _id(start_id,"start_id")
  if start_id not in self.nodes:raise TraceError("unknown impact node")
  adjacent={n:set() for n in self.nodes}
  for e in self.edges:adjacent[e.source_id].add(e.target_id);adjacent[e.target_id].add(e.source_id)
  seen={start_id};todo=[start_id]
  while todo:
   n=todo.pop()
   for x in adjacent[n]:
    if x not in seen:seen.add(x);todo.append(x)
  return tuple(sorted(seen))
