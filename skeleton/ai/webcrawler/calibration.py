"""Calibration metrics for probabilistic research confidence."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class CalibrationReport:
 count:int;brier:float;ece:float
def calibration_report(predictions,outcomes,*,bins=10):
 p=tuple(float(x) for x in predictions);y=tuple(int(x) for x in outcomes)
 if len(p)!=len(y) or not p:raise ValueError("predictions/outcomes must be equal and non-empty")
 if bins<1:raise ValueError("bins must be positive")
 if any(x<0 or x>1 for x in p) or any(x not in (0,1) for x in y):raise ValueError("invalid calibration values")
 brier=sum((a-b)**2 for a,b in zip(p,y))/len(p);ece=0.
 for i in range(bins):
  lo=i/bins;hi=(i+1)/bins
  idx=[j for j,x in enumerate(p) if lo<=x<(hi if i<bins-1 else hi+1e-12)]
  if not idx:continue
  conf=sum(p[j] for j in idx)/len(idx);acc=sum(y[j] for j in idx)/len(idx)
  ece+=len(idx)/len(p)*abs(conf-acc)
 return CalibrationReport(len(p),brier,ece)
