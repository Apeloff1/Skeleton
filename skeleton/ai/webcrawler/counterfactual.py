"""Counterfactual evidence sensitivity: measure conclusion dependence on individual evidence."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class EvidenceInfluence:
 observation_id:str;baseline:float;without:float;delta:float
def leave_one_out_influence(evidence,*,now):
 baseline=float(evidence.assurance(now=now)["score"]);out=[]
 original=dict(evidence.observations)
 try:
  for oid in sorted(original):
   evidence.observations={k:v for k,v in original.items() if k!=oid}
   score=float(evidence.assurance(now=now)["score"])
   out.append(EvidenceInfluence(oid,baseline,score,baseline-score))
 finally:evidence.observations=original
 return tuple(sorted(out,key=lambda x:(-abs(x.delta),x.observation_id)))
