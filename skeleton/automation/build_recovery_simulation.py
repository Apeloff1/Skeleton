"""Pure recovery simulation over every transaction crash phase."""
from __future__ import annotations
from dataclasses import dataclass
from .build_crash_matrix import matrix
from .build_resume import decide
@dataclass(frozen=True)
class SimulationResult:
 phase:str;expected:str;observed:str;passed:bool
def simulate(head:str="a"*40)->tuple[SimulationResult,...]:
 out=[]
 for x in matrix():
  phase=None if x.phase=="before_prepare" else x.phase
  d=decide(saved_head=head,current_head=head,journal_phase=phase,receipt_present=x.phase in {"validated","committed","published"},baseline_matches=True)
  expected={"restart":"continue","rollback":"rollback_task","reconcile_receipt":"continue","retire_journal":"retire_journal","verify_publication":"continue"}[x.action]
  # validated with a surviving receipt is already a durable boundary.
  if x.phase=="validated":expected="continue"
  out.append(SimulationResult(x.phase,expected,d.action,d.action==expected))
 return tuple(out)
