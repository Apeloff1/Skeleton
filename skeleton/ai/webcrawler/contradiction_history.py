"""Track contradiction persistence across historical regimes."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class ContradictionPersistence:
 regime_start:int;regime_end:int;positive_hosts:int;negative_hosts:int;contested:bool;balance:float
def contradiction_persistence(observations,regimes):
 out=[]
 for regime in regimes:
  pos=set();neg=set()
  for obs in observations:
   if not any(regime.start_year<=y<=regime.end_year for y in obs.signal_years):continue
   (neg if obs.polarity<0 else pos).add(obs.host)
  total=len(pos|neg);balance=min(len(pos),len(neg))/max(1,total)
  out.append(ContradictionPersistence(regime.start_year,regime.end_year,len(pos),len(neg),bool(pos and neg),balance))
 return tuple(out)
def persistent_contestation(rows,*,minimum_regimes=2):
 if minimum_regimes<1:raise ValueError("minimum_regimes must be positive")
 contested=[x for x in rows if x.contested]
 return {"contested_regimes":len(contested),"persistent":len(contested)>=minimum_regimes,
         "mean_balance":sum(x.balance for x in contested)/max(1,len(contested))}
