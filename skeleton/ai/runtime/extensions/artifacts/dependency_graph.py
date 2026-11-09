from dataclasses import dataclass
@dataclass(frozen=True)
class ArtifactNode: artifact_id:str; version:str; artifact_class:str
@dataclass(frozen=True)
class ArtifactDependency: source:str; source_version:str; target:str; target_version:str; kind:str
@dataclass(frozen=True)
class ArtifactGraph:
 nodes:tuple[ArtifactNode,...]; edges:tuple[ArtifactDependency,...]
 def __post_init__(self):
  if any(not n.artifact_id or not n.version or not n.artifact_class for n in self.nodes):raise ValueError("complete artifact node identity required")
  known={(n.artifact_id,n.version) for n in self.nodes}
  if len(known)!=len(self.nodes):raise ValueError("duplicate artifact node")
  if any(not e.kind for e in self.edges):raise ValueError("dependency kind required")
  edge_ids={(e.source,e.source_version,e.target,e.target_version,e.kind) for e in self.edges}
  if len(edge_ids)!=len(self.edges):raise ValueError("duplicate artifact dependency")
  g={x:[] for x in known}
  for e in self.edges:
   a=(e.source,e.source_version);b=(e.target,e.target_version)
   if a not in known or b not in known:raise ValueError("wrong/missing version dependency")
   g[a].append(b)
  visiting=set();done=set()
  def visit(n):
   if n in visiting:raise ValueError("artifact dependency cycle")
   if n in done:return
   visiting.add(n)
   for x in g[n]:visit(x)
   visiting.remove(n);done.add(n)
  for n in known:visit(n)
 def dependencies(self,a,v):return tuple(e for e in self.edges if e.source==a and e.source_version==v)
