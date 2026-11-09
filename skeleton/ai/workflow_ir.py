"""Versioned workflow intermediate representation for VOL-306."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from skeleton.contracts.canonical import canonical_json_bytes
IR_VERSION=1
@dataclass(frozen=True)
class WorkflowNode:
 node_id:str; capability:str; inputs:tuple[str,...]=(); outputs:tuple[str,...]=(); authority:str="none"; retries:int=0; timeout_seconds:int=60; compensation:str|None=None
 def __post_init__(self):
  if not self.node_id or not self.capability: raise ValueError("node identity/capability required")
  if self.retries<0 or self.timeout_seconds<=0: raise ValueError("invalid retry/timeout")
  if not self.authority or self.authority.strip()!=self.authority: raise ValueError("authority must be explicit")
@dataclass(frozen=True,order=True)
class WorkflowEdge:
 source:str; target:str
@dataclass(frozen=True)
class WorkflowIR:
 workflow_id:str; nodes:tuple[WorkflowNode,...]; edges:tuple[WorkflowEdge,...]; version:int=IR_VERSION
 def __post_init__(self):
  if self.version!=IR_VERSION: raise ValueError("unsupported workflow IR version")
  ids=[n.node_id for n in self.nodes]
  if not self.workflow_id or len(ids)!=len(set(ids)): raise ValueError("workflow id and unique nodes required")
  known=set(ids)
  if any(e.source not in known or e.target not in known or e.source==e.target for e in self.edges): raise ValueError("invalid edge")
  graph={i:[] for i in ids}
  for e in self.edges: graph[e.source].append(e.target)
  visiting=set(); done=set()
  def visit(n):
   if n in visiting: raise ValueError("workflow DAG contains cycle")
   if n in done:return
   visiting.add(n)
   for x in graph[n]: visit(x)
   visiting.remove(n);done.add(n)
  for n in ids:visit(n)
 def payload(self):
  return {"version":self.version,"workflow_id":self.workflow_id,"nodes":[{"node_id":n.node_id,"capability":n.capability,"inputs":list(n.inputs),"outputs":list(n.outputs),"authority":n.authority,"retries":n.retries,"timeout_seconds":n.timeout_seconds,"compensation":n.compensation} for n in sorted(self.nodes,key=lambda x:x.node_id)],"edges":[{"source":e.source,"target":e.target} for e in sorted(self.edges)]}
 @property
 def digest(self):return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()
