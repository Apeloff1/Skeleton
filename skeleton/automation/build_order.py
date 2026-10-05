"""Deterministic construction DAG for VOL-109."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class BuildOrderError(ValueError):pass
class DependencyKind(str,Enum): HARD="hard"; SOFT="soft"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise BuildOrderError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class BuildDependency:
 upstream_id:str;downstream_id:str;kind:DependencyKind
 def __post_init__(self):
  object.__setattr__(self,"upstream_id",_id(self.upstream_id,"upstream_id"));object.__setattr__(self,"downstream_id",_id(self.downstream_id,"downstream_id"))
  if self.upstream_id==self.downstream_id:raise BuildOrderError("self dependency")
@dataclass(frozen=True,slots=True)
class BuildStopCondition:
 node_id:str;condition_id:str;active:bool;reason:str
 def __post_init__(self):
  object.__setattr__(self,"node_id",_id(self.node_id,"node_id"));object.__setattr__(self,"condition_id",_id(self.condition_id,"condition_id"))
  if self.active and not self.reason.strip():raise BuildOrderError("active stop requires reason")
class BuildOrder:
 def __init__(self,node_ids,dependencies=(),stops=()):
  self.nodes=tuple(sorted(set(_id(x,"node_id") for x in node_ids)));self.dependencies=tuple(dependencies);self.stops=tuple(stops)
  known=set(self.nodes)
  for d in self.dependencies:
   if d.upstream_id not in known or d.downstream_id not in known:raise BuildOrderError("dangling dependency")
  for s in self.stops:
   if s.node_id not in known:raise BuildOrderError("dangling stop condition")
  self._assert_acyclic()
 def _assert_acyclic(self):
  graph={n:[] for n in self.nodes}
  for d in self.dependencies:
   if d.kind is DependencyKind.HARD:graph[d.upstream_id].append(d.downstream_id)
  state={}
  def visit(n):
   if state.get(n)==1:raise BuildOrderError("hard dependency cycle")
   if state.get(n)==2:return
   state[n]=1
   for x in graph[n]:visit(x)
   state[n]=2
  for n in self.nodes:visit(n)
 def blocked_reasons(self,node_id,completed):
  _id(node_id,"node_id");done=set(completed);out=[]
  for d in self.dependencies:
   if d.downstream_id==node_id and d.kind is DependencyKind.HARD and d.upstream_id not in done:out.append("dependency:"+d.upstream_id)
  out.extend("stop:"+s.condition_id+":"+s.reason for s in self.stops if s.node_id==node_id and s.active)
  return tuple(sorted(out))
 def ready(self,completed):
  done=set(completed);return tuple(n for n in self.nodes if n not in done and not self.blocked_reasons(n,done))
 def maturity_allowed(self,node_id,completed):return not self.blocked_reasons(node_id,completed)
