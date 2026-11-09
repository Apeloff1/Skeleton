"""Bayesian source-quality learning from resolved evidence outcomes."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class SourcePosterior:
 source:str;alpha:float;beta:float
 @property
 def mean(self):return self.alpha/(self.alpha+self.beta)
 @property
 def strength(self):return self.alpha+self.beta
def update_source_quality(source,*,correct,incorrect,prior_alpha=1.,prior_beta=1.):
 if correct<0 or incorrect<0 or prior_alpha<=0 or prior_beta<=0:raise ValueError("invalid source quality update")
 return SourcePosterior(source,prior_alpha+correct,prior_beta+incorrect)
def conservative_quality(posterior,*,shrink=4.):
 return (posterior.alpha)/(posterior.alpha+posterior.beta+shrink)
