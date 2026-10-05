"""Bounded roadmap-control contracts for VOL-118.

This module does not replace canonical plan/build authorities. It records typed
links and immutable revisions while requiring explicit ADR authority for
breadth-freeze scope additions.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, re

_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class RoadmapError(ValueError): pass

def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v): raise RoadmapError(f"{f} must be stable identifier")
 return v

@dataclass(frozen=True,slots=True)
class RoadmapDependency:
 upstream_id:str; downstream_id:str
 def __post_init__(self):
  object.__setattr__(self,"upstream_id",_id(self.upstream_id,"upstream_id"));object.__setattr__(self,"downstream_id",_id(self.downstream_id,"downstream_id"))
  if self.upstream_id==self.downstream_id: raise RoadmapError("self dependency")

@dataclass(frozen=True,slots=True)
class RoadmapItem:
 item_id:str;work_package_id:str;build_node_id:str;risk_ids:tuple[str,...];acceptance_gate_ids:tuple[str,...];top_level_scope:bool=False;architecture_decision_id:str|None=None
 def __post_init__(self):
  for f in ("item_id","work_package_id","build_node_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  if not isinstance(self.risk_ids,tuple) or not isinstance(self.acceptance_gate_ids,tuple):raise RoadmapError("risk and gate links must be tuples")
  risks=tuple(_id(x,"risk_id") for x in self.risk_ids);gates=tuple(_id(x,"acceptance_gate_id") for x in self.acceptance_gate_ids)
  if len(set(risks))!=len(risks) or len(set(gates))!=len(gates):raise RoadmapError("duplicate roadmap link")
  if not gates:raise RoadmapError("acceptance gate required")
  if not isinstance(self.top_level_scope,bool):raise RoadmapError("top_level_scope must be bool")
  if self.architecture_decision_id is not None:object.__setattr__(self,"architecture_decision_id",_id(self.architecture_decision_id,"architecture_decision_id"))
  if self.top_level_scope and self.architecture_decision_id is None:raise RoadmapError("breadth-freeze scope addition requires architecture decision")
  object.__setattr__(self,"risk_ids",tuple(sorted(risks)));object.__setattr__(self,"acceptance_gate_ids",tuple(sorted(gates)))

@dataclass(frozen=True,slots=True)
class RoadmapRevision:
 revision_id:str;parent_revision_id:str|None;assumption_digest:str;rationale:str;item_ids:tuple[str,...]
 def __post_init__(self):
  object.__setattr__(self,"revision_id",_id(self.revision_id,"revision_id"))
  if self.parent_revision_id is not None:object.__setattr__(self,"parent_revision_id",_id(self.parent_revision_id,"parent_revision_id"))
  if self.parent_revision_id==self.revision_id:raise RoadmapError("revision cannot parent itself")
  if not isinstance(self.assumption_digest,str) or not re.fullmatch(r"[0-9a-f]{64}",self.assumption_digest):raise RoadmapError("assumption_digest must be sha256")
  if not isinstance(self.rationale,str) or not self.rationale.strip():raise RoadmapError("revision rationale required")
  if not isinstance(self.item_ids,tuple) or not self.item_ids:raise RoadmapError("revision item_ids required")
  ids=tuple(_id(x,"item_id") for x in self.item_ids)
  if len(set(ids))!=len(ids):raise RoadmapError("duplicate revision item")
  object.__setattr__(self,"item_ids",tuple(sorted(ids)))

class RoadmapControl:
 def __init__(self,items,dependencies=()):
  if not isinstance(items,tuple) or not items or any(not isinstance(x,RoadmapItem) for x in items):raise RoadmapError("items must be non-empty typed tuple")
  if not isinstance(dependencies,tuple) or any(not isinstance(x,RoadmapDependency) for x in dependencies):raise RoadmapError("dependencies must be typed tuple")
  if len({x.item_id for x in items})!=len(items):raise RoadmapError("duplicate roadmap item")
  if len(set(dependencies))!=len(dependencies):raise RoadmapError("duplicate roadmap dependency")
  self.items={x.item_id:x for x in items};self.dependencies=dependencies;self.revisions={}
  for d in dependencies:
   if d.upstream_id not in self.items or d.downstream_id not in self.items:raise RoadmapError("unknown roadmap dependency")
  self._reject_cycles()
 def _reject_cycles(self):
  edges={x:set() for x in self.items}
  for d in self.dependencies:edges[d.upstream_id].add(d.downstream_id)
  visiting=set();visited=set()
  def visit(n):
   if n in visiting:raise RoadmapError("roadmap dependency cycle")
   if n in visited:return
   visiting.add(n)
   for x in sorted(edges[n]):visit(x)
   visiting.remove(n);visited.add(n)
  for n in sorted(edges):visit(n)
 def add_revision(self,revision):
  if not isinstance(revision,RoadmapRevision):raise RoadmapError("revision must be RoadmapRevision")
  if revision.revision_id in self.revisions:raise RoadmapError("duplicate roadmap revision")
  if set(revision.item_ids)-set(self.items):raise RoadmapError("revision references unknown item")
  if revision.parent_revision_id is None:
   if self.revisions:raise RoadmapError("only first revision may be root")
  elif revision.parent_revision_id not in self.revisions:raise RoadmapError("unknown revision parent")
  self.revisions[revision.revision_id]=revision
  return revision
