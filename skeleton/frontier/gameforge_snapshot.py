"""Small immutable runtime state snapshot for bounded observability."""
from dataclasses import dataclass
@dataclass(frozen=True)
class RuntimeSnapshot:
 lifecycle:str
 dependencies_ready:bool
 active:int
 budget_used:int
 budget_capacity:int
 quota_used:int=0
 queue_depth:int=0
 health:float=1.0
 def saturated(self): return self.active>=self.budget_capacity or self.quota_used>=self.budget_capacity
