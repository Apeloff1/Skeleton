"""Governed control-plane, objective and workflow IR contracts VOL-300..306."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .contracts import sha256_json

class ObjectiveState(str,Enum): REQUESTED="requested"; ACTIVE="active"; SATISFIED="satisfied"; ABANDONED="abandoned"
@dataclass(frozen=True,slots=True)
class ObjectiveCriterion: criterion_id:str; description:str; measurable:bool
@dataclass(frozen=True,slots=True)
class Objective:
 objective_id:str; requested_text:str; criteria:tuple[ObjectiveCriterion,...]; state:ObjectiveState; inferred_subgoal:bool=False
@dataclass(frozen=True,slots=True)
class ObjectiveAssumption: statement:str; evidence:str|None
@dataclass(frozen=True,slots=True)
class ObjectiveAmbiguity: description:str; high_impact:bool
@dataclass(frozen=True,slots=True)
class NormalizedObjective:
 objective:Objective; assumptions:tuple[ObjectiveAssumption,...]; ambiguities:tuple[ObjectiveAmbiguity,...]; clarified:bool=False
 @property
 def executable(self)->bool:return self.clarified or not any(a.high_impact for a in self.ambiguities)

class ConstraintStrength(str,Enum): HARD="hard"; SOFT="soft"
@dataclass(frozen=True,slots=True)
class Constraint: constraint_id:str; strength:ConstraintStrength; predicate:str; provenance:str
@dataclass(frozen=True,slots=True)
class ConstraintSet: constraints:tuple[Constraint,...]
@dataclass(frozen=True,slots=True)
class ConstraintResult: admissible:bool; violated:tuple[str,...]; conflicts:tuple[str,...]
def evaluate_constraints(cs:ConstraintSet,satisfied:dict[str,bool])->ConstraintResult:
 bad=tuple(c.constraint_id for c in cs.constraints if not satisfied.get(c.constraint_id,False))
 hard=any(c.strength is ConstraintStrength.HARD and c.constraint_id in bad for c in cs.constraints)
 return ConstraintResult(not hard,bad,())

@dataclass(frozen=True,slots=True)
class DecisionOption: option_id:str; admissible:bool; utility:float; evidence:tuple[str,...]; uncertainty:float
@dataclass(frozen=True,slots=True)
class DecisionContext: objective_id:str; constraint_result:ConstraintResult; options:tuple[DecisionOption,...]
@dataclass(frozen=True,slots=True)
class Decision: option_id:str|None; reason:str
def decide(c:DecisionContext)->Decision:
 if not c.constraint_result.admissible:return Decision(None,"hard constraint failure")
 options=[o for o in c.options if o.admissible]
 if not options:return Decision(None,"no admissible option")
 return Decision(max(options,key=lambda o:o.utility).option_id,"best admissible utility")

@dataclass(frozen=True,slots=True)
class DecisionRecord:
 record_id:str; decision:Decision; context_digest:str; supersedes:str|None=None
@dataclass(frozen=True,slots=True)
class DecisionEdge: record_id:str; target_kind:str; target_id:str
@dataclass(frozen=True,slots=True)
class DecisionOutcome: record_id:str; result_digest:str; success:bool

@dataclass(frozen=True,slots=True)
class WorkflowNode:
 node_id:str; capability:str; authority:tuple[str,...]; retries:int; timeout_ms:int; compensation_node:str|None
 def __post_init__(self):
  if self.retries<0 or self.timeout_ms<=0:raise ValueError("invalid retry/timeout")
@dataclass(frozen=True,slots=True)
class WorkflowEdge: source:str; target:str
@dataclass(frozen=True,slots=True)
class WorkflowIR:
 version:str; nodes:tuple[WorkflowNode,...]; edges:tuple[WorkflowEdge,...]
 @property
 def identity(self)->str:
  return sha256_json({"version":self.version,"nodes":[(n.node_id,n.capability,n.authority,n.retries,n.timeout_ms,n.compensation_node) for n in self.nodes],"edges":[(e.source,e.target) for e in self.edges]})

@dataclass(frozen=True,slots=True)
class ControlPlaneCommand:
 command_id:str; workflow:WorkflowIR; objective_id:str; policy_receipt:str; authority_receipt:str
@dataclass(frozen=True,slots=True)
class ControlPlaneState:
 revision:int; workflow_identity:str|None; last_command_id:str|None; durable_state_digest:str
@dataclass(frozen=True,slots=True)
class ControlPlaneReceipt:
 command_id:str; previous_revision:int; revision:int; accepted:bool; reason:str
def apply_command(state:ControlPlaneState,command:ControlPlaneCommand,*,policy_valid:bool,authority_valid:bool)->tuple[ControlPlaneState,ControlPlaneReceipt]:
 if not policy_valid or not authority_valid:
  return state,ControlPlaneReceipt(command.command_id,state.revision,state.revision,False,"independent gate rejected")
 new=ControlPlaneState(state.revision+1,command.workflow.identity,command.command_id,sha256_json({"previous":state.durable_state_digest,"command":command.command_id,"workflow":command.workflow.identity}))
 return new,ControlPlaneReceipt(command.command_id,state.revision,new.revision,True,"accepted")
