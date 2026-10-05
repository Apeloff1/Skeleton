"""Deterministic static workflow compiler for VOL-308."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from skeleton.contracts.canonical import canonical_json_bytes
@dataclass(frozen=True,order=True)
class WorkflowLink: source:str; target:str
@dataclass(frozen=True)
class CompiledWorkflow:
 workflow_id:str; nodes:tuple[str,...]; links:tuple[WorkflowLink,...]; capabilities:tuple[str,...]
 @property
 def digest(self):return hashlib.sha256(canonical_json_bytes({"workflow_id":self.workflow_id,"nodes":list(self.nodes),"links":[{"source":x.source,"target":x.target} for x in self.links],"capabilities":list(self.capabilities)})).hexdigest()
@dataclass(frozen=True)
class CompileResult:
 workflow:CompiledWorkflow|None; diagnostics:tuple[str,...]
 @property
 def ok(self):return self.workflow is not None and not self.diagnostics
def compile_workflow(workflow_id,nodes,links,required_capabilities,available_capabilities,compensations):
 node_items=tuple(nodes); link_items=tuple(links); required=tuple(required_capabilities); available=tuple(available_capabilities)
 ids=tuple(sorted(set(node_items))); diags=[]
 if not workflow_id:diags.append("missing-workflow-id")
 if len(ids)!=len(node_items):diags.append("duplicate-node")
 missing=sorted(set(required)-set(available))
 if missing:diags.extend("missing-capability:"+x for x in missing)
 known=set(ids)
 for link in link_items:
  if link.source not in known or link.target not in known:diags.append("invalid-link")
 for node,target in compensations.items():
  if node not in known or target not in known or node==target:diags.append("invalid-compensation:"+node)
 graph={n:[] for n in ids}
 for e in link_items:
  if e.source in known and e.target in known:graph[e.source].append(e.target)
 visiting=set();done=set()
 def visit(n):
  if n in visiting:raise ValueError
  if n in done:return
  visiting.add(n)
  for x in graph[n]:visit(x)
  visiting.remove(n);done.add(n)
 try:
  for n in ids:visit(n)
 except ValueError:diags.append("cycle")
 if diags:return CompileResult(None,tuple(sorted(set(diags))))
 return CompileResult(CompiledWorkflow(workflow_id,ids,tuple(sorted(link_items)),tuple(sorted(set(required)))),())
