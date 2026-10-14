"""Sequential evidence test for bounded autonomous research decisions."""
from __future__ import annotations
from dataclasses import dataclass
import math
@dataclass(frozen=True)
class SequentialDecision:
 log_likelihood_ratio:float;lower:float;upper:float;action:str;samples:int
def sequential_bernoulli(successes,failures,*,p0=.5,p1=.75,alpha=.05,beta=.05):
 if successes<0 or failures<0 or not 0<p0<p1<1 or not 0<alpha<1 or not 0<beta<1:raise ValueError("invalid sequential test")
 n=successes+failures
 llr=successes*math.log(p1/p0)+failures*math.log((1-p1)/(1-p0))
 lower=math.log(beta/(1-alpha));upper=math.log((1-beta)/alpha)
 action="accept-high" if llr>=upper else ("accept-low" if llr<=lower else "continue")
 return SequentialDecision(llr,lower,upper,action,n)
