"""Approximate multi-source interaction attribution for research assurance."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,random
@dataclass(frozen=True)
class SourceAttribution:
 observation_id:str;contribution:float;samples:int
def approximate_shapley(evidence,*,now,samples=128,seed_key=""):
 ids=tuple(sorted(evidence.observations))
 if not ids:return ()
 if samples<16:raise ValueError("samples must be >= 16")
 original=dict(evidence.observations);rng=random.Random(int(hashlib.sha256((seed_key+"|"+repr(ids)).encode()).hexdigest()[:16],16))
 totals={x:0. for x in ids}
 try:
  for _ in range(samples):
   order=list(ids);rng.shuffle(order);active={};evidence.observations={}
   prev=float(evidence.assurance(now=now)["score"])
   for oid in order:
    active[oid]=original[oid];evidence.observations=dict(active)
    score=float(evidence.assurance(now=now)["score"]);totals[oid]+=score-prev;prev=score
 finally:evidence.observations=original
 return tuple(SourceAttribution(x,totals[x]/samples,samples) for x in sorted(ids,key=lambda x:(-abs(totals[x]),x)))
