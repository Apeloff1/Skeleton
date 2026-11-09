"""Completion cannot hide unresolved autonomous repair work."""
from __future__ import annotations
def require_repair_closure(states:dict[str,str])->None:
 unresolved={k:v for k,v in states.items() if v not in {"retired","quarantined"}}
 if unresolved:raise ValueError(f"unresolved repair work: {sorted(unresolved)}")
