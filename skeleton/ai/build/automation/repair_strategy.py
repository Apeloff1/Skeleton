"""Bounded escalation policy for repeated empirical repair failures."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class RepairStrategy:
 attempt:int;mode:str;context_budget:int
def strategy(attempt:int)->RepairStrategy:
 if attempt==1:return RepairStrategy(1,"minimal_local_fix",12000)
 if attempt==2:return RepairStrategy(2,"dependency_context_fix",20000)
 if attempt==3:return RepairStrategy(3,"integration_root_cause",28000)
 raise ValueError("repair strategy budget exhausted")
