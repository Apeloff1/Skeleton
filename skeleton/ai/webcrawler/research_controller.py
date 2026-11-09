"""Budget-bound autonomous research controller."""
from __future__ import annotations
from dataclasses import dataclass
from .information_gain import expected_binary_information_gain
@dataclass(frozen=True)
class ControllerCandidate:
 action_id:str;action_type:str;sensitivity:float;specificity:float;cost:float;latency:float
@dataclass(frozen=True)
class ControllerChoice:
 action_id:str;utility:float;information_gain:float;reason:str
def choose_next_action(prior,candidates,*,budget,cost_weight=.25,latency_weight=.05):
 if budget<0:raise ValueError("budget must be non-negative")
 out=[]
 for c in candidates:
  if c.cost>budget:continue
  ig=expected_binary_information_gain(prior,sensitivity=c.sensitivity,specificity=c.specificity).gain
  utility=ig-cost_weight*c.cost-latency_weight*c.latency
  out.append(ControllerChoice(c.action_id,utility,ig,"max-expected-information-utility"))
 return max(out,key=lambda x:(x.utility,x.information_gain,x.action_id)) if out else None
