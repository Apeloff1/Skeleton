"""Bounded dependency-block diagnosis without inventing work."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class DependencyRepair:
 task_id:str;missing:tuple[str,...];action:str
def diagnose(task_id:str,dependencies:tuple[str,...],known:set[str],done:set[str])->DependencyRepair:
 missing=tuple(sorted(set(dependencies)-known))
 if missing:return DependencyRepair(task_id,missing,"quarantine")
 unresolved=tuple(sorted(set(dependencies)-done))
 return DependencyRepair(task_id,unresolved,"wait" if unresolved else "ready")
