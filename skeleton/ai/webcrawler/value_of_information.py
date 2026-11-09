"""Decision-theoretic expected value of information for research actions."""
from __future__ import annotations
from dataclasses import dataclass
import math
@dataclass(frozen=True)
class ResearchAction:
 action_id:str;expected_information_gain:float;success_probability:float;cost:float;latency_penalty:float=0.
@dataclass(frozen=True)
class ActionValue:
 action_id:str;value:float;expected_gain:float;cost:float
def rank_actions(actions,*,cost_weight=.25,latency_weight=.1):
 out=[]
 for a in actions:
  vals=(a.expected_information_gain,a.success_probability,a.cost,a.latency_penalty)
  if any(not math.isfinite(float(x)) or float(x)<0 for x in vals):raise ValueError("action values must be finite and non-negative")
  gain=min(1.,a.expected_information_gain)*min(1.,a.success_probability)
  value=gain-cost_weight*a.cost-latency_weight*a.latency_penalty
  out.append(ActionValue(a.action_id,value,gain,a.cost))
 return tuple(sorted(out,key=lambda x:(-x.value,x.action_id)))
