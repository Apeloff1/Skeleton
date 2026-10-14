"""Gate learned change points using evidence uncertainty and support."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class ChangePointDecision:
 year:int;accepted:bool;raw_score:float;support:int;uncertainty:float;adjusted_score:float
def gate_change_points(points,signals,uncertainty_by_year=None,*,min_support=2,min_adjusted=.35):
 uncertainty_by_year=uncertainty_by_year or {};out=[]
 for p in points:
  row=signals.get(p.year,{})
  support=int(row.get("distinct_hosts",0));u=max(0.,min(1.,float(uncertainty_by_year.get(p.year,0))))
  adjusted=p.score*(1-u)*min(1.,support/max(1,min_support))
  out.append(ChangePointDecision(p.year,support>=min_support and adjusted>=min_adjusted,p.score,support,u,adjusted))
 return tuple(out)
