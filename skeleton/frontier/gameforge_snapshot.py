"""Small immutable runtime state snapshot for observability."""
from dataclasses import dataclass
@dataclass(frozen=True)
class RuntimeSnapshot:
 lifecycle:str
 dependencies_ready:bool
 active:int
 budget_used:int
 budget_capacity:int
 def saturated(self): return self.active>=self.budget_capacity
