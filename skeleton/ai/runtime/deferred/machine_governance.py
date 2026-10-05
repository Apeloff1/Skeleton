"""Machine-governance and release evidence contracts for VOL-268..272."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import sha256_json

def _t(v:object,n:str)->str:
 if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} must be non-empty text")
 return v.strip()
def _d(v:object,n:str)->str:
 v=_t(v,n)
 if len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ValueError(f"{n} must be lowercase sha256")
 return v

@dataclass(frozen=True,slots=True)
class ReviewOwner: owner:str
@dataclass(frozen=True,slots=True)
class CodeownersRule:
 path_pattern:str; owners:tuple[ReviewOwner,...]
 def __post_init__(self):
  object.__setattr__(self,"path_pattern",_t(self.path_pattern,"path_pattern"))
  if not self.owners: raise ValueError("CODEOWNERS rule requires owner")
@dataclass(frozen=True,slots=True)
class SensitiveOwnership:
 path_pattern:str; fixed_reviewers:tuple[ReviewOwner,...]
@dataclass(frozen=True,slots=True)
class CodeownersManifest:
 rules:tuple[CodeownersRule,...]; sensitive:tuple[SensitiveOwnership,...]
 def render(self)->str:
  rows=[]
  for r in sorted(self.rules,key=lambda x:x.path_pattern): rows.append(r.path_pattern+" "+" ".join(sorted(o.owner for o in r.owners)))
  for s in sorted(self.sensitive,key=lambda x:x.path_pattern): rows.append(s.path_pattern+" "+" ".join(sorted(o.owner for o in s.fixed_reviewers)))
  return "\n".join(rows)+"\n"
 @property
 def digest(self)->str: return sha256_json({"rendered":self.render()})

@dataclass(frozen=True,slots=True)
class DocReference:
 path:str; target:str; target_digest:str
 def __post_init__(self): object.__setattr__(self,"target_digest",_d(self.target_digest,"target_digest"))
@dataclass(frozen=True,slots=True)
class DocumentationRule:
 normative:bool; authority_source:str|None
 def __post_init__(self):
  if self.normative and not self.authority_source: raise ValueError("normative documentation must declare authority source")
@dataclass(frozen=True,slots=True)
class DocCheck:
 reference:DocReference; exists:bool; observed_digest:str|None
 @property
 def valid(self)->bool: return self.exists and self.observed_digest==self.reference.target_digest

@dataclass(frozen=True,slots=True)
class DiagramSource:
 model_id:str; model_version:str; model_digest:str
 def __post_init__(self): object.__setattr__(self,"model_digest",_d(self.model_digest,"model_digest"))
@dataclass(frozen=True,slots=True)
class DiagramSpec:
 diagram_id:str; source:DiagramSource; format:str
@dataclass(frozen=True,slots=True)
class DiagramArtifact:
 spec:DiagramSpec; rendered_digest:str; embedded_source_digest:str
 def __post_init__(self):
  object.__setattr__(self,"rendered_digest",_d(self.rendered_digest,"rendered_digest")); object.__setattr__(self,"embedded_source_digest",_d(self.embedded_source_digest,"embedded_source_digest"))
 @property
 def current(self)->bool: return self.embedded_source_digest==self.spec.source.model_digest

@dataclass(frozen=True,slots=True)
class ArchitectureSnapshot:
 snapshot_id:str; manifest_digest:str; dependency_graph_digest:str; release_id:str
 def __post_init__(self):
  for n in ("manifest_digest","dependency_graph_digest"): object.__setattr__(self,n,_d(getattr(self,n),n))
 @property
 def digest(self)->str: return sha256_json({"id":self.snapshot_id,"manifest":self.manifest_digest,"dependencies":self.dependency_graph_digest,"release":self.release_id})
@dataclass(frozen=True,slots=True)
class ArchitectureDiff:
 before:str; after:str; manifest_changed:bool; dependency_graph_changed:bool
def diff_architecture(a:ArchitectureSnapshot,b:ArchitectureSnapshot)->ArchitectureDiff:
 return ArchitectureDiff(a.digest,b.digest,a.manifest_digest!=b.manifest_digest,a.dependency_graph_digest!=b.dependency_graph_digest)

@dataclass(frozen=True,slots=True)
class ReproBuild:
 build_id:str; source_digest:str; environment_digest:str; toolchain_digest:str; artifact_digest:str
 def __post_init__(self):
  for n in ("source_digest","environment_digest","toolchain_digest","artifact_digest"): object.__setattr__(self,n,_d(getattr(self,n),n))
@dataclass(frozen=True,slots=True)
class BuildVariance:
 field:str; left:str; right:str
@dataclass(frozen=True,slots=True)
class ArtifactComparison:
 left:ReproBuild; right:ReproBuild; variances:tuple[BuildVariance,...]
 @property
 def reproducible(self)->bool:
  return self.left.source_digest==self.right.source_digest and self.left.environment_digest==self.right.environment_digest and self.left.toolchain_digest==self.right.toolchain_digest and self.left.artifact_digest==self.right.artifact_digest and not self.variances
def compare_builds(a:ReproBuild,b:ReproBuild)->ArtifactComparison:
 vs=[]
 for f in ("source_digest","environment_digest","toolchain_digest","artifact_digest"):
  if getattr(a,f)!=getattr(b,f): vs.append(BuildVariance(f,getattr(a,f),getattr(b,f)))
 return ArtifactComparison(a,b,tuple(vs))
