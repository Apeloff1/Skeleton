"""Workflow language/versioning and task semantics VOL-307..312."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .contracts import sha256_json

@dataclass(frozen=True,slots=True)
class DSLVersion: major:int; minor:int
@dataclass(frozen=True,slots=True)
class WorkflowSource: source_id:str; version:DSLVersion; text:str; declared_authority:tuple[str,...]
@dataclass(frozen=True,slots=True)
class DSLDiagnostic: code:str; message:str; position:int|None
def validate_source(s:WorkflowSource,allowed_authority:tuple[str,...])->tuple[DSLDiagnostic,...]:
 ds=[]
 if s.version.major!=1:ds.append(DSLDiagnostic("DSL_VERSION","unsupported DSL major",None))
 extra=set(s.declared_authority)-set(allowed_authority)
 if extra:ds.append(DSLDiagnostic("DSL_AUTHORITY","undeclared privilege: "+",".join(sorted(extra)),None))
 if "\x00" in s.text:ds.append(DSLDiagnostic("DSL_SYNTAX","NUL is not valid source",s.text.index("\x00")))
 return tuple(ds)

@dataclass(frozen=True,slots=True)
class WorkflowLink: node_id:str; capability:str; compensation:str|None
@dataclass(frozen=True,slots=True)
class CompiledWorkflow: source_id:str; source_digest:str; version:DSLVersion; links:tuple[WorkflowLink,...]
 @property
 def identity(self)->str:return sha256_json({"source":self.source_digest,"version":(self.version.major,self.version.minor),"links":[(x.node_id,x.capability,x.compensation) for x in self.links]})
@dataclass(frozen=True,slots=True)
class CompileResult: workflow:CompiledWorkflow|None; diagnostics:tuple[DSLDiagnostic,...]
def compile_workflow(s:WorkflowSource,links:tuple[WorkflowLink,...],available_capabilities:tuple[str,...],edges:tuple[tuple[str,str],...])->CompileResult:
 ds=list(validate_source(s,s.declared_authority))
 nodes={x.node_id for x in links}
 for x in links:
  if x.capability not in available_capabilities:ds.append(DSLDiagnostic("MISSING_CAPABILITY",x.capability,None))
  if x.compensation and x.compensation not in nodes:ds.append(DSLDiagnostic("INVALID_COMPENSATION",x.node_id,None))
 graph={n:[] for n in nodes}
 for a,b in edges:
  if a in graph:graph[a].append(b)
 visiting=set();done=set()
 def visit(n):
  if n in visiting:return True
  if n in done:return False
  visiting.add(n)
  if any(visit(x) for x in graph.get(n,())):return True
  visiting.remove(n);done.add(n);return False
 if any(visit(n) for n in nodes):ds.append(DSLDiagnostic("CYCLE","workflow contains cycle",None))
 if ds:return CompileResult(None,tuple(ds))
 d=sha256_json({"text":s.text,"version":(s.version.major,s.version.minor)})
 return CompileResult(CompiledWorkflow(s.source_id,d,s.version,tuple(sorted(links,key=lambda x:x.node_id))),())

@dataclass(frozen=True,slots=True)
class WorkflowVersion: workflow_id:str; version:int; ir_digest:str
@dataclass(frozen=True,slots=True)
class WorkflowCompatibility: source_version:int; target_version:int; compatible:bool
@dataclass(frozen=True,slots=True)
class WorkflowBinding: run_id:str; workflow:WorkflowVersion
def rebind(b:WorkflowBinding,target:WorkflowVersion,c:WorkflowCompatibility,*,explicit_migration:bool)->WorkflowBinding:
 if not explicit_migration:return b
 if b.workflow.version!=c.source_version or target.version!=c.target_version or not c.compatible:raise ValueError("incompatible workflow migration")
 return WorkflowBinding(b.run_id,target)

@dataclass(frozen=True,slots=True)
class StateMapping: source_key:str; target_key:str; irreversible:bool=False
@dataclass(frozen=True,slots=True)
class WorkflowMigration: migration_id:str; source_version:int; target_version:int; mappings:tuple[StateMapping,...]; rollback_declared:bool
@dataclass(frozen=True,slots=True)
class WorkflowMigrationReceipt: migration_id:str; migrated:bool; pinned:bool; restarted:bool
def migrate(m:WorkflowMigration,*,compatible:bool,terminate_and_restart:bool=False)->WorkflowMigrationReceipt:
 irreversible=any(x.irreversible for x in m.mappings)
 if irreversible and m.rollback_declared:raise ValueError("irreversible migration cannot claim rollback")
 if compatible:return WorkflowMigrationReceipt(m.migration_id,True,False,False)
 return WorkflowMigrationReceipt(m.migration_id,False,not terminate_and_restart,terminate_and_restart)

class TaskType(str,Enum): GENERIC="generic"; RESEARCH="research"; CODE="code"; OPERATIONS="operations"
@dataclass(frozen=True,slots=True)
class TaskProfile: task_type:TaskType; default_budget:int; default_tests:tuple[str,...]; authority:tuple[str,...]=()
@dataclass(frozen=True,slots=True)
class TaskClassification: task_type:TaskType; confidence:float; profile:TaskProfile
def classify(label:str,profiles:dict[TaskType,TaskProfile])->TaskClassification:
 try:t=TaskType(label.lower())
 except ValueError:t=TaskType.GENERIC
 return TaskClassification(t,1.0 if t is not TaskType.GENERIC else 0.0,profiles[t])

@dataclass(frozen=True,slots=True)
class ComplexityFeature: name:str; value:float
@dataclass(frozen=True,slots=True)
class ComplexityEstimate: score:float; uncertainty:float; calibration_id:str; features:tuple[ComplexityFeature,...]
@dataclass(frozen=True,slots=True)
class EstimateRevision: previous:ComplexityEstimate; revised:ComplexityEstimate; runtime_evidence:str
def revise(e:ComplexityEstimate,new_score:float,new_uncertainty:float,evidence:str)->EstimateRevision:
 return EstimateRevision(e,ComplexityEstimate(new_score,new_uncertainty,e.calibration_id,e.features),evidence)
