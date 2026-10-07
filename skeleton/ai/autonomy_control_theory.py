"""Bounded feedback control primitives for VOL-317."""
from dataclasses import dataclass
@dataclass(frozen=True)
class ControlState:
 observed:float; target:float; previous_error:float=0.0
@dataclass(frozen=True)
class ControlSignal:
 requested:float; applied:float; lower_bound:float; upper_bound:float; clamped:bool; oscillating:bool
@dataclass(frozen=True)
class AutonomyController:
 gain:float; lower_bound:float; upper_bound:float
 def __post_init__(self):
  if self.gain<0 or self.lower_bound>self.upper_bound:raise ValueError("invalid controller bounds")
 def evaluate(self,state:ControlState):
  error=state.target-state.observed; requested=self.gain*error
  applied=min(self.upper_bound,max(self.lower_bound,requested))
  oscillating=state.previous_error!=0 and error!=0 and (state.previous_error>0)!=(error>0)
  return ControlSignal(requested,applied,self.lower_bound,self.upper_bound,applied!=requested,oscillating)
def bounded_control(controller,state,*,policy_limit,resource_limit):
 if policy_limit<0 or resource_limit<0:raise ValueError("limits must be nonnegative")
 raw=controller.evaluate(state); upper=min(raw.upper_bound,policy_limit,resource_limit)
 applied=min(upper,max(raw.lower_bound,raw.requested))
 return ControlSignal(raw.requested,applied,raw.lower_bound,upper,applied!=raw.requested,raw.oscillating)
