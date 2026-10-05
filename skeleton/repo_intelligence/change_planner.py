"""Change planning bound to repository graph identity."""
from dataclasses import dataclass
from .repository_graph import RepositoryGraph,RepositoryGraphError
@dataclass(frozen=True,slots=True)
class ChangePlan:
 graph_digest:str;changed_paths:tuple[str,...];impacted_paths:tuple[str,...];required_tests:tuple[str,...];owners:tuple[str,...];authority_scope:str="change-plan-only"
 def __post_init__(self):
  if self.authority_scope!="change-plan-only":raise RepositoryGraphError("plan cannot grant mutation authority")
def plan_change(graph:RepositoryGraph,changed_paths:tuple[str,...])->ChangePlan:
 if not isinstance(graph,RepositoryGraph) or not isinstance(changed_paths,tuple) or not changed_paths:raise RepositoryGraphError("typed graph and changed paths required")
 changed=tuple(sorted(set(changed_paths)))
 return ChangePlan(graph.digest,changed,graph.impact(changed),graph.tests_for(changed),graph.owners_for(changed))
