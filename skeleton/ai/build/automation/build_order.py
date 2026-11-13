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
  if not isinstance(self.kind,DependencyKind):raise BuildOrderError("dependency kind must be DependencyKind")
  if self.upstream_id==self.downstream_id:raise BuildOrderError("self dependency")
@dataclass(frozen=True,slots=True)
class BuildStopCondition:
 node_id:str;condition_id:str;active:bool;reason:str
 def __post_init__(self):
  object.__setattr__(self,"node_id",_id(self.node_id,"node_id"));object.__setattr__(self,"condition_id",_id(self.condition_id,"condition_id"))
  if not isinstance(self.active,bool):raise BuildOrderError("stop active must be bool")
  if not isinstance(self.reason,str):raise BuildOrderError("stop reason must be str")
  if self.active and not self.reason.strip():raise BuildOrderError("active stop requires reason")
class BuildOrder:
 def __init__(self,node_ids,dependencies=(),stops=()):
  if not isinstance(node_ids,tuple) or not node_ids:raise BuildOrderError("node_ids must be non-empty tuple")
  if not isinstance(dependencies,tuple) or any(not isinstance(x,BuildDependency) for x in dependencies):raise BuildOrderError("dependencies must be typed tuple")
  if not isinstance(stops,tuple) or any(not isinstance(x,BuildStopCondition) for x in stops):raise BuildOrderError("stops must be typed tuple")
  normalized=tuple(_id(x,"node_id") for x in node_ids)
  if len(set(normalized))!=len(normalized):raise BuildOrderError("duplicate node identity")
  if len(set(dependencies))!=len(dependencies):raise BuildOrderError("duplicate dependency")
  if len({(s.node_id,s.condition_id) for s in stops})!=len(stops):raise BuildOrderError("duplicate stop condition")
  self.nodes=tuple(sorted(normalized));self.dependencies=dependencies;self.stops=stops
  known=set(self.nodes)
  for d in self.dependencies:
   if d.upstream_id not in known or d.downstream_id not in known:raise BuildOrderError("dangling dependency")
  for s in self.stops:
   if s.node_id not in known:raise BuildOrderError("dangling stop condition")
  self._assert_acyclic()
 def _assert_acyclic(self):
  # Kahn's algorithm avoids Python recursion limits on deep production DAGs.
  # Soft dependencies are advisory: they cannot cause a hard-order cycle.
  from collections import deque
  successors={n:[] for n in self.nodes}
  incoming={n:0 for n in self.nodes}
  for dependency in self.dependencies:
   if dependency.kind is DependencyKind.HARD:
    successors[dependency.upstream_id].append(dependency.downstream_id)
    incoming[dependency.downstream_id]+=1
  queue=deque(node for node in self.nodes if incoming[node]==0)
  visited=0
  while queue:
   node=queue.popleft()
   visited+=1
   for downstream in successors[node]:
    incoming[downstream]-=1
    if incoming[downstream]==0:queue.append(downstream)
  if visited!=len(self.nodes):raise BuildOrderError("hard dependency cycle")
 def _completed(self,completed):
  if not isinstance(completed,(tuple,list,set,frozenset)):raise BuildOrderError("completed must be a bounded collection")
  done=set(_id(x,"completed_node_id") for x in completed)
  if len(done)!=len(completed):raise BuildOrderError("duplicate completed node")
  if len(completed)>len(self.nodes):raise BuildOrderError("completed exceeds construction graph bound")
  if not done.issubset(set(self.nodes)):raise BuildOrderError("completed contains unknown node")
  return done
 def _blocked_lookup(self,done):
  """Index all hard blockers and active stops in one deterministic graph pass."""
  messages={node:[] for node in self.nodes}
  for dependency in self.dependencies:
   if dependency.kind is DependencyKind.HARD and dependency.upstream_id not in done:
    messages[dependency.downstream_id].append("dependency:"+dependency.upstream_id)
  for stop in self.stops:
   if stop.active:
    messages[stop.node_id].append("stop:"+stop.condition_id+":"+stop.reason)
  return {node:tuple(sorted(reasons)) for node,reasons in messages.items()}
 def blocked_reasons(self,node_id,completed):
  _id(node_id,"node_id")
  if node_id not in self.nodes:raise BuildOrderError("unknown node")
  done=self._completed(completed)
  return self._blocked_lookup(done)[node_id]
 def ready(self,completed):
  done=self._completed(completed)
  blockers=self._blocked_lookup(done)
  return tuple(node for node in self.nodes if node not in done and not blockers[node])
 def maturity_allowed(self,node_id,completed):
  done=self._completed(completed)
  if node_id in done:raise BuildOrderError("completed node cannot request new maturity promotion")
  return not self.blocked_reasons(node_id,tuple(sorted(done)))

 def snapshot(self,completed):
  done=self._completed(completed)
  blockers=self._blocked_lookup(done)
  return tuple((node,node in done,blockers[node]) for node in self.nodes)
