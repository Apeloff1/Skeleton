"""Human trust, intent, workspace and resource contracts VOL-326..334."""
from dataclasses import dataclass
from enum import Enum
@dataclass(frozen=True,slots=True)
class HumanFactorRequirement: requirement_id:str; consequence_visible:bool; authority_visible:bool; status_visible:bool
@dataclass(frozen=True,slots=True)
class OperatorTask: task_id:str; risk:str; workload:int
@dataclass(frozen=True,slots=True)
class HumanFactorFinding: task_id:str; requirement_id:str; passed:bool
@dataclass(frozen=True,slots=True)
class ApprovalScope: scope_id:str; version:str; expires_at:str; authority:frozenset[str]
@dataclass(frozen=True,slots=True)
class ApprovalBurden: approvals:int; overrides:int; stale:int
@dataclass(frozen=True,slots=True)
class ApprovalReusePolicy: max_uses:int; require_same_version:bool=True
def reusable(scope,requested_scope,requested_version,uses,policy):
 if not all((scope.scope_id,scope.version,requested_scope,requested_version)) or policy.max_uses<1 or uses<0:return False
 return scope.scope_id==requested_scope and (not policy.require_same_version or scope.version==requested_version) and uses<policy.max_uses
@dataclass(frozen=True,slots=True)
class TrustSignal: confidence:float; uncertainty:float; degraded:bool; evidence:tuple[str,...]
@dataclass(frozen=True,slots=True)
class CalibrationObservation: predicted:float; observed:float
@dataclass(frozen=True,slots=True)
class TrustPresentation: confidence:float; uncertainty:float; degraded:bool; evidence_count:int
def present_trust(s):
 if not 0<=s.confidence<=1 or not 0<=s.uncertainty<=1 or any(not e for e in s.evidence):raise ValueError("invalid trust signal")
 return TrustPresentation(s.confidence,s.uncertainty,s.degraded,len(s.evidence))
@dataclass(frozen=True,slots=True)
class IntentConstraint: key:str; value:str
@dataclass(frozen=True,slots=True)
class UserIntent: intent_id:str; authoritative_instruction:str; inferred_intent:str|None; constraints:tuple[IntentConstraint,...]
@dataclass(frozen=True,slots=True)
class IntentRevision: revision_id:str; intent:UserIntent; supersedes:str|None
def latest_intent(revisions):
 if not revisions or any(not r.revision_id or not r.intent.intent_id or not r.intent.authoritative_instruction for r in revisions):raise ValueError("complete intent identity required")
 if len({r.revision_id for r in revisions})!=len(revisions):raise ValueError("duplicate intent revision")
 superseded={r.supersedes for r in revisions if r.supersedes}
 live=[r for r in revisions if r.revision_id not in superseded]
 if len(live)!=1:raise ValueError("ambiguous intent lineage")
 return live[0]
@dataclass(frozen=True,slots=True)
class ProjectFact: fact_id:str; value:str; source:str; trust_class:str
@dataclass(frozen=True,slots=True)
class ProjectMemoryRevision: revision_id:str; fact:ProjectFact; supersedes:str|None
@dataclass(frozen=True,slots=True)
class ProjectMemory: tenant_id:str; project_id:str; trust_class:str; revisions:tuple[ProjectMemoryRevision,...]
def read_project_memory(m,tenant,project,trust):
 if not all((m.tenant_id,m.project_id,m.trust_class,tenant,project,trust)):return ()
 if len({r.revision_id for r in m.revisions})!=len(m.revisions) or any(not all((r.revision_id,r.fact.fact_id,r.fact.source,r.fact.trust_class)) for r in m.revisions):return ()
 if (m.tenant_id,m.project_id,m.trust_class)!=(tenant,project,trust):return ()
 return m.revisions
@dataclass(frozen=True,slots=True)
class WorkspaceMember: principal_id:str; permissions:frozenset[str]; active:bool=True
@dataclass(frozen=True,slots=True)
class WorkspaceResource: resource_ref:str
@dataclass(frozen=True,slots=True)
class Workspace: workspace_id:str; members:tuple[WorkspaceMember,...]; resources:tuple[WorkspaceResource,...]
def member_authorized(w,principal,permission):
 if not w.workspace_id or not principal or not permission or len({m.principal_id for m in w.members})!=len(w.members):return False
 return any(m.principal_id==principal and m.active and permission in m.permissions for m in w.members)
@dataclass(frozen=True,slots=True)
class ResourceName:
 tenant:str; project:str; name:str; version:str
    def __post_init__(self):
        if not all((self.tenant, self.project, self.name, self.version)):
            raise ValueError("resource scope required")
        if any(x in self.name for x in ("..", "/", "\\", "%2f", "%2F")) or self.name != self.name.strip():
            raise ValueError("ambiguous resource name")
@dataclass(frozen=True,slots=True)
class ResourceNamespace: tenant:str; project:str
@dataclass(frozen=True,slots=True)
class ResourceRef: name:ResourceName
@dataclass(frozen=True,slots=True)
class ResourceQuery: namespace:ResourceNamespace; name:str; version:str|None
@dataclass(frozen=True,slots=True)
class ResourceHandle: ref:ResourceRef; lifecycle:str
@dataclass(frozen=True,slots=True)
class ResolutionReceipt: query:ResourceQuery; resolved_version:str|None; authorized:bool; alias_used:bool
def resolve(q,candidates,*,authorized):
 if not all((q.namespace.tenant,q.namespace.project,q.name)) or q.version=="":raise ValueError("complete resource query identity required")
 if len({(x.name.tenant,x.name.project,x.name.name,x.name.version) for x in candidates})!=len(candidates):raise ValueError("duplicate resource identity")
 if not authorized:return None,ResolutionReceipt(q,None,False,False)
 matches=[x for x in candidates if x.name.tenant==q.namespace.tenant and x.name.project==q.namespace.project and x.name.name==q.name]
 if q.version:matches=[x for x in matches if x.name.version==q.version]
 if len(matches)!=1:return None,ResolutionReceipt(q,None,True,q.version is None)
 return ResourceHandle(matches[0],"active"),ResolutionReceipt(q,matches[0].name.version,True,q.version is None)
class DependencyKind(str,Enum): BUILD="build"; RUNTIME="runtime"; EVIDENCE="evidence"
@dataclass(frozen=True,slots=True)
class ArtifactNode: artifact_id:str; version:str
@dataclass(frozen=True,slots=True)
class ArtifactDependency: source:ArtifactNode; target:ArtifactNode; kind:DependencyKind
@dataclass(frozen=True,slots=True)
class ArtifactGraph: nodes:tuple[ArtifactNode,...]; edges:tuple[ArtifactDependency,...]
def artifact_cycle(g):
 ids=[(n.artifact_id,n.version) for n in g.nodes]
 if any(not all(x) for x in ids) or len(set(ids))!=len(ids):raise ValueError("unique artifact node identity required")
 known=set(ids)
 if any((e.source.artifact_id,e.source.version) not in known or (e.target.artifact_id,e.target.version) not in known for e in g.edges):raise ValueError("artifact edge endpoint missing")
 adj={x:[] for x in ids}
 for e in g.edges:adj[(e.source.artifact_id,e.source.version)].append((e.target.artifact_id,e.target.version))
 active=set();done=set()
 def visit(n):
  if n in active:return True
  if n in done:return False
  active.add(n)
  if any(visit(x) for x in adj.get(n,())):return True
  active.remove(n);done.add(n);return False
 return any(visit(n) for n in adj)
