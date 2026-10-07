from dataclasses import dataclass
_REQUIRED_GATES=frozenset({"ownership","compatibility","risk"})
@dataclass(frozen=True)
class ChangeGate: name:str; passed:bool; evidence_id:str
@dataclass(frozen=True)
class ChangeStep: step_id:str; reversible:bool; rollback:str|None
@dataclass(frozen=True)
class SafeChangePlan:
 steps:tuple[ChangeStep,...]; gates:tuple[ChangeGate,...]; budget:int; estimated_cost:int; uncertain:bool
 def __post_init__(self):
  if isinstance(self.budget,bool) or isinstance(self.estimated_cost,bool) or self.budget<0 or self.estimated_cost<0:raise ValueError("nonnegative numeric budget required")
  if not self.steps or self.estimated_cost>self.budget:raise ValueError("missing steps or budget exceeded")
  if len({s.step_id for s in self.steps})!=len(self.steps):raise ValueError("change step IDs must be unique")
  names={g.name for g in self.gates}
  if len(names)!=len(self.gates):raise ValueError("duplicate change gate")
  if not _REQUIRED_GATES.issubset(names):raise PermissionError("required ownership/compatibility/risk gates missing")
  if any(g.passed is not True or not g.evidence_id for g in self.gates):raise PermissionError("ownership/compatibility/risk gate failed")
  if not isinstance(self.uncertain,bool):raise ValueError("uncertainty must be explicit boolean")
  if self.uncertain and any(not s.reversible or not s.rollback for s in self.steps):raise ValueError("uncertain work must be reversible with rollback")
