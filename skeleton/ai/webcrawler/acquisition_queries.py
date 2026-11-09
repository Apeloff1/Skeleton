"""Synthesize deterministic evidence-acquisition queries from historical targets."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class AcquisitionQuery:
 query:str;start_year:int;end_year:int;reason:str
def synthesize_acquisition_queries(base_query,targets,*,per_target=3):
 if not base_query.strip():raise ValueError("base query required")
 if per_target<1:raise ValueError("per_target must be positive")
 out=[]
 for t in targets:
  span=f"{t.start_year} {t.end_year}" if t.start_year!=t.end_year else str(t.start_year)
  variants=(f'{base_query} {span} history',f'{base_query} {span} report archive',f'{base_query} {span} evidence study')
  reason="+".join(t.reasons)
  out.extend(AcquisitionQuery(q,t.start_year,t.end_year,reason) for q in variants[:per_target])
 return tuple(out)
