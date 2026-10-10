"""Learn research-action success, cost and latency from completed runs."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class ActionEconomics:
 action_type:str;attempts:int;successes:int;mean_cost:float;mean_latency:float
 @property
 def success_probability(self):return (self.successes+1)/(self.attempts+2)
def update_action_economics(prior,*,success,cost,latency):
 if cost<0 or latency<0:raise ValueError("cost and latency must be non-negative")
 if prior is None:return ActionEconomics("unknown",1,int(bool(success)),float(cost),float(latency))
 n=prior.attempts+1
 return ActionEconomics(prior.action_type,n,prior.successes+int(bool(success)),prior.mean_cost+(cost-prior.mean_cost)/n,prior.mean_latency+(latency-prior.mean_latency)/n)
