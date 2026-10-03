"""Machine-checkable completion objective for an autonomous build."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class BuildObjective:
 id:str;required_gates:tuple[str,...];required_predicates:tuple[str,...];max_cycles:int=80
 def validate(self):
  if not self.id or not self.required_gates or not self.required_predicates:raise ValueError("incomplete build objective")
  if self.max_cycles<1 or self.max_cycles>200:raise ValueError("unsafe cycle budget")
  if len(self.required_gates)!=len(set(self.required_gates)):raise ValueError("duplicate required gates")
