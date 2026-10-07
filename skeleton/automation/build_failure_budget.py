"""Per-category failure budgets stop pathological autonomous loops."""
from __future__ import annotations
from dataclasses import dataclass
DEFAULT_LIMITS={"validation":4,"integration_ci":3,"portability":2,"repository_hygiene":2,"code_quality":3,"unknown":1}
@dataclass(frozen=True)
class FailureBudget:
 counts:dict[str,int]
 def record(self,category:str):
  n=dict(self.counts);n[category]=n.get(category,0)+1
  if n[category]>DEFAULT_LIMITS.get(category,1):raise ValueError(f"failure budget exhausted: {category}")
  return FailureBudget(n)
