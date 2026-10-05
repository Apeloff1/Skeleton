from dataclasses import dataclass
@dataclass(frozen=True)
class ChangeGate: name:str; passed:bool; evidence_id:str
@dataclass(frozen=True)
class ChangeStep: step_id:str; reversible:bool; rollback:str|None
@dataclass(frozen=True)
class SafeChangePlan:
 steps:tuple[ChangeStep,...]; gates:tuple[ChangeGate,...]; budget:int; estimated_cost:int; uncertain:bool
 def __post_init__(self):
  if not self.steps or self.estimated_cost>self.budget:raise ValueError("missing steps or budget exceeded")
  if any(not g.passed or not g.evidence_id for g in self.gates):raise PermissionError("ownership/compatibility/risk gate failed")
  if self.uncertain and any(not s.reversible or not s.rollback for s in self.steps):raise ValueError("uncertain work must be reversible with rollback")
