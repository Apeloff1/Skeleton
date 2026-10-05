"""Project/tenant/trust isolated memory for VOL-330."""
from dataclasses import dataclass
@dataclass(frozen=True)
class ProjectFact:
 fact_id:str; tenant_id:str; project_id:str; trust_class:str; value:str; source_id:str; supersedes:str|None=None
@dataclass(frozen=True)
class ProjectMemoryRevision: previous_id:str; current_id:str; source_id:str
@dataclass(frozen=True)
class ProjectMemory:
 tenant_id:str; project_id:str; trust_class:str; facts:tuple[ProjectFact,...]=()
 def add(self,fact:ProjectFact):
  if not fact.fact_id or not fact.source_id:raise ValueError("fact and source identity required")
  if (fact.tenant_id,fact.project_id,fact.trust_class)!=(self.tenant_id,self.project_id,self.trust_class):raise PermissionError("cross-boundary memory write")
  ids={x.fact_id for x in self.facts}
  if fact.fact_id in ids:raise ValueError("fact identity is append-only")
  if fact.supersedes and fact.supersedes not in ids:raise ValueError("supersession target missing")
  if fact.supersedes and any(x.supersedes==fact.supersedes for x in self.facts):raise ValueError("supersession fork requires explicit reconciliation")
  return ProjectMemory(self.tenant_id,self.project_id,self.trust_class,self.facts+(fact,))
 def visible(self,tenant_id,project_id,trust_class):
  if (tenant_id,project_id,trust_class)!=(self.tenant_id,self.project_id,self.trust_class):raise PermissionError("cross-boundary memory read")
  superseded={x.supersedes for x in self.facts if x.supersedes}
  return tuple(x for x in self.facts if x.fact_id not in superseded)
