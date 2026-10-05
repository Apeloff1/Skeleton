"""Deterministic cross-language repository dependency graph."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import re
from types import MappingProxyType
from typing import Mapping
from skeleton.contracts.canonical import canonical_json_bytes
MAX_FILES=100000;MAX_EDGES=500000
class RepositoryGraphError(ValueError):pass
_EXT={".py":"python",".ts":"typescript",".tsx":"typescript",".js":"javascript",".java":"java",".rs":"rust",".go":"go"}
@dataclass(frozen=True,slots=True)
class FileNode:
 path:str;language:str;content_digest:str;owner:str|None=None;tests:tuple[str,...]=()
 def __post_init__(self):
  if not isinstance(self.path,str) or not self.path or self.path.startswith("/") or ".." in self.path.split("/"):raise RepositoryGraphError("invalid path")
  if self.language not in set(_EXT.values()):raise RepositoryGraphError("unsupported language")
  if not isinstance(self.content_digest,str) or not re.fullmatch(r"[0-9a-f]{64}",self.content_digest):raise RepositoryGraphError("invalid digest")
  if self.owner is not None and (not isinstance(self.owner,str) or not self.owner):raise RepositoryGraphError("invalid owner")
  if not isinstance(self.tests,tuple) or any(not isinstance(x,str) or not x or x.startswith("/") or ".." in x.split("/") for x in self.tests):raise RepositoryGraphError("tests must be safe non-empty paths")
  object.__setattr__(self,"tests",tuple(sorted(set(self.tests))))
@dataclass(frozen=True,slots=True)
class DependencyEdge:
 source:str;target:str;kind:str
 def __post_init__(self):
  for value in (self.source,self.target):
   if not isinstance(value,str) or not value or value.startswith("/") or ".." in value.split("/"):raise RepositoryGraphError("invalid edge path")
  if self.kind not in {"import","test","ownership","generated"}:raise RepositoryGraphError("invalid edge kind")
  if self.source==self.target:raise RepositoryGraphError("self edge")
class RepositoryGraph:
 def __init__(self,nodes:tuple[FileNode,...],edges:tuple[DependencyEdge,...]):
  if not isinstance(nodes,tuple) or not isinstance(edges,tuple):raise RepositoryGraphError("nodes and edges must be tuples")
  if any(not isinstance(n,FileNode) for n in nodes) or any(not isinstance(e,DependencyEdge) for e in edges):raise RepositoryGraphError("typed nodes and edges required")
  if len(nodes)>MAX_FILES or len(edges)>MAX_EDGES:raise RepositoryGraphError("graph budget exceeded")
  by={n.path:n for n in nodes}
  if len(by)!=len(nodes):raise RepositoryGraphError("duplicate path")
  for e in edges:
   if e.source not in by or e.target not in by:raise RepositoryGraphError("dangling edge")
  self.nodes=MappingProxyType(dict(sorted(by.items())))
  self.edges=tuple(sorted(set((e.source,e.target,e.kind) for e in edges)))
 @property
 def digest(self):return sha256(canonical_json_bytes({"nodes":[{"path":n.path,"language":n.language,"digest":n.content_digest,"owner":n.owner,"tests":n.tests} for n in self.nodes.values()],"edges":self.edges})).hexdigest()
 def impact(self,paths:tuple[str,...])->tuple[str,...]:
  if any(p not in self.nodes for p in paths):raise RepositoryGraphError("unknown changed path")
  impacted=set(paths);changed=True
  while changed:
   changed=False
   for source,target,kind in self.edges:
    if target in impacted and source not in impacted and kind in {"import","test","generated"}:impacted.add(source);changed=True
  return tuple(sorted(impacted))
 def tests_for(self,paths:tuple[str,...])->tuple[str,...]:
  out=set()
  for p in self.impact(paths):out.update(self.nodes[p].tests)
  return tuple(sorted(out))
 def owners_for(self,paths:tuple[str,...])->tuple[str,...]:
  return tuple(sorted({self.nodes[p].owner for p in self.impact(paths) if self.nodes[p].owner}))
