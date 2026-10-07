"""Posterior entropy and expected information gain for binary research claims."""
from __future__ import annotations
from dataclasses import dataclass
import math
@dataclass(frozen=True)
class InformationGain:
 prior_entropy:float;expected_posterior_entropy:float;gain:float
def binary_entropy(p):
 p=float(p)
 if not 0<=p<=1:raise ValueError("probability must be in [0,1]")
 if p in (0.,1.):return 0.
 return -(p*math.log2(p)+(1-p)*math.log2(1-p))
def expected_binary_information_gain(prior,*,sensitivity,specificity):
 prior=float(prior);se=float(sensitivity);sp=float(specificity)
 if any(not 0<=x<=1 for x in (prior,se,sp)):raise ValueError("probabilities must be in [0,1]")
 pos=prior*se+(1-prior)*(1-sp);neg=1-pos
 def post(num,den):return prior if den==0 else num/den
 p_pos=post(prior*se,pos);p_neg=post(prior*(1-se),neg)
 expected=pos*binary_entropy(p_pos)+neg*binary_entropy(p_neg)
 h=binary_entropy(prior)
 return InformationGain(h,expected,max(0.,h-expected))
