"""Deterministic empirical calibration for Jeeves policy reliability."""
from __future__ import annotations
from dataclasses import dataclass,field
from typing import Mapping
@dataclass
class PolicyStats:
 attempts:int=0; successes:int=0; reward:float=0.
 @property
 def success_rate(self): return self.successes/self.attempts if self.attempts else 0.
@dataclass
class PolicyCalibrator:
 stats:dict[str,PolicyStats]=field(default_factory=dict); learning_rate:float=.2
 def __post_init__(self):
  if not 0<self.learning_rate<=1: raise ValueError("learning_rate must be in (0, 1]")
 def observe(self,action:str,*,reward:float,successful:bool):
  reward=max(-1.,min(1.,reward)); s=self.stats.setdefault(action,PolicyStats()); s.attempts+=1; s.successes+=int(successful); s.reward=s.reward*(1-self.learning_rate)+reward*self.learning_rate; return s
 def reliability(self,action):
  s=self.stats.get(action)
  if not s or not s.attempts:return .5
  return max(0.,min(1.,.6*s.success_rate+.4*((s.reward+1)/2)))
 def ranking(self): return tuple(sorted(((a,self.reliability(a)) for a in self.stats),key=lambda x:(-x[1],x[0])))
 def snapshot(self)->Mapping[str,float]: return {a:self.reliability(a) for a in sorted(self.stats)}
