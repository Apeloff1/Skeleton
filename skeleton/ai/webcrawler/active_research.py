"""Active temporal evidence acquisition driven by uncertainty, bias and contestation."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class AcquisitionTarget:
 start_year:int;end_year:int;priority:float;reasons:tuple[str,...]
def plan_acquisition(*,regimes,bias_rows,contradiction_rows=(),uncertainty_by_regime=None,limit=10):
 if limit<1:raise ValueError("limit must be positive")
 uncertainty_by_regime=uncertainty_by_regime or {};bias={x.bucket:x for x in bias_rows};contr={x.regime_start:x for x in contradiction_rows}
 out=[]
 for r in regimes:
  decade=(r.start_year//10)*10;b=bias.get(decade);c=contr.get(r.start_year);u=float(uncertainty_by_regime.get(r.start_year,0))
  score=0.0;reasons=[]
  if b and b.risk>.35:score+=.35*b.risk;reasons.append("historical-bias")
  if c and c.contested:score+=.30*(.5+c.balance/2);reasons.append("persistent-contestation")
  if u>.25:score+=.25*min(1,u);reasons.append("signal-uncertainty")
  if r.strength<.75:score+=.10*(1-r.strength);reasons.append("sparse-regime")
  if reasons:out.append(AcquisitionTarget(r.start_year,r.end_year,min(1,score),tuple(reasons)))
 return tuple(sorted(out,key=lambda x:(-x.priority,x.start_year,x.end_year))[:limit])
