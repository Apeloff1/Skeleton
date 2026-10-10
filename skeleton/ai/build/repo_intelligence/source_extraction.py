"""Conservative cross-language dependency extraction for VOL-021."""
from __future__ import annotations
import ast,re
from hashlib import sha256
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping
from .repository_graph import DependencyEdge,FileNode,RepositoryGraph,RepositoryGraphError
MAX_SOURCE_BYTES=2_000_000
_EXT={".py":"python",".js":"javascript",".ts":"typescript",".tsx":"typescript",".java":"java",".rs":"rust",".go":"go"}
@dataclass(frozen=True,slots=True)
class SourceFile:
 path:str;content:str;content_digest:str;owner:str|None=None;tests:tuple[str,...]=()
 def __post_init__(self):
  if not isinstance(self.path,str) or not self.path or self.path.startswith("/") or ".." in self.path.split("/"):raise RepositoryGraphError("invalid source path")
  if not isinstance(self.content,str):raise RepositoryGraphError("source content must be str")
  if not isinstance(self.content_digest,str) or not re.fullmatch(r"[0-9a-f]{64}",self.content_digest):raise RepositoryGraphError("invalid source digest")
  if sha256(self.content.encode()).hexdigest()!=self.content_digest:raise RepositoryGraphError("source digest mismatch")
  if self.owner is not None and (not isinstance(self.owner,str) or not self.owner):raise RepositoryGraphError("invalid source owner")
  if not isinstance(self.tests,tuple) or any(not isinstance(x,str) or not x for x in self.tests):raise RepositoryGraphError("source tests must be non-empty strings")
  object.__setattr__(self,"tests",tuple(sorted(set(self.tests))))
def _specs(src:SourceFile)->tuple[str,...]:
 if len(src.content.encode())>MAX_SOURCE_BYTES:raise RepositoryGraphError("source budget exceeded")
 ext=PurePosixPath(src.path).suffix;lang=_EXT.get(ext)
 if not lang:raise RepositoryGraphError("unsupported source extension")
 if lang=="python":
  try: tree=ast.parse(src.content)
  except SyntaxError as e:raise RepositoryGraphError("invalid python source") from e
  out=[]
  for n in ast.walk(tree):
   if isinstance(n,ast.Import):out.extend(x.name for x in n.names)
   elif isinstance(n,ast.ImportFrom) and n.module:out.append(n.module)
  return tuple(sorted(set(out)))
 patterns={
 "javascript":r"(?:from\s+|require\s*\(\s*)['\"]([^'\"]+)['\"]",
 "typescript":r"(?:from\s+|require\s*\(\s*)['\"]([^'\"]+)['\"]",
 "java":r"(?m)^\s*import\s+(?:static\s+)?([\w.]+)",
 "rust":r"(?m)^\s*(?:use|mod)\s+([A-Za-z_][\w:]*)",
 "go":r"(?m)^\s*import\s+(?:[\w.]+\s+)?[\"\x27]([^\"\x27]+)[\"\x27]",
 }
 return tuple(sorted(set(re.findall(patterns[lang],src.content))))
def _resolve(source:str,spec:str,paths:set[str])->str|None:
 base=PurePosixPath(source).parent
 if spec.startswith("."):
  depth=len(spec)-len(spec.lstrip("."))
  remainder=spec[depth:]
  root=base
  for _ in range(max(0,depth-1)):root=root.parent
  rel=remainder.replace(".","/").lstrip("/")
  raw=str(root/rel) if rel else str(root)
  candidates=[raw,raw+".py",raw+".js",raw+".ts",raw+".tsx",raw+"/__init__.py",raw+"/index.js",raw+"/index.ts"]
 else:
  dotted=spec.replace("::","/").replace(".","/")
  candidates=[dotted+e for e in _EXT]+[dotted+"/__init__.py",dotted+"/index.js",dotted+"/index.ts"]
 matches=[p for p in candidates if p in paths]
 return matches[0] if len(matches)==1 else None
def build_repository_graph(sources:tuple[SourceFile,...])->RepositoryGraph:
 if not isinstance(sources,tuple):raise RepositoryGraphError("sources must be tuple")
 paths={s.path for s in sources}
 nodes=[];edges=[]
 for s in sources:
  ext=PurePosixPath(s.path).suffix
  if ext not in _EXT:raise RepositoryGraphError("unsupported source extension")
  nodes.append(FileNode(s.path,_EXT[ext],s.content_digest,s.owner,s.tests))
 for s in sources:
  for spec in _specs(s):
   target=_resolve(s.path,spec,paths)
   if target and target!=s.path:edges.append(DependencyEdge(s.path,target,"import"))
 return RepositoryGraph(tuple(nodes),tuple(edges))
