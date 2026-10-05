"""Change planning bound to repository graph identity."""
from dataclasses import dataclass
import re
from .repository_graph import RepositoryGraph,RepositoryGraphError
@dataclass(frozen=True,slots=True)
class ChangePlan:
 graph_digest:str;changed_paths:tuple[str,...];impacted_paths:tuple[str,...];required_tests:tuple[str,...];owners:tuple[str,...];authority_scope:str="change-plan-only"
 def __post_init__(self):
  if not isinstance(self.graph_digest,str) or not re.fullmatch(r"[0-9a-f]{64}",self.graph_digest):raise RepositoryGraphError("invalid graph digest")
  for name,value in (("changed_paths",self.changed_paths),("impacted_paths",self.impacted_paths),("required_tests",self.required_tests),("owners",self.owners)):
   if not isinstance(value,tuple) or any(not isinstance(x,str) or not x for x in value):raise RepositoryGraphError(f"{name} must be non-empty strings")
   if value!=tuple(sorted(set(value))):raise RepositoryGraphError(f"{name} must be canonical")
  if not self.changed_paths:raise RepositoryGraphError("changed paths required")
  if not set(self.changed_paths).issubset(self.impacted_paths):raise RepositoryGraphError("changed paths must be impacted")
  if self.authority_scope!="change-plan-only":raise RepositoryGraphError("plan cannot grant mutation authority")
def plan_change(graph:RepositoryGraph,changed_paths:tuple[str,...])->ChangePlan:
 if not isinstance(graph,RepositoryGraph) or not isinstance(changed_paths,tuple) or not changed_paths:raise RepositoryGraphError("typed graph and changed paths required")
 changed=tuple(sorted(set(changed_paths)))
 return ChangePlan(graph.digest,changed,graph.impact(changed),graph.tests_for(changed),graph.owners_for(changed))
