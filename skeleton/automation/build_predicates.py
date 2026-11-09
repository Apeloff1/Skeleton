"""Evaluate explicit build completion predicates."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class PredicateResult:
 name:str;satisfied:bool;evidence:str
def require_all(results:tuple[PredicateResult,...],required:tuple[str,...])->None:
 by={r.name:r for r in results}
 missing=set(required)-set(by)
 if missing:raise ValueError(f"missing completion predicates: {sorted(missing)}")
 failed=[n for n in required if not by[n].satisfied]
 if failed:raise ValueError(f"unsatisfied completion predicates: {failed}")
