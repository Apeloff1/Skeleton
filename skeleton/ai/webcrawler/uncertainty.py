"""Uncertainty estimates for historical signal and regime decisions."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,random
@dataclass(frozen=True)
class Interval:
 low:float;center:float;high:float;samples:int
def deterministic_bootstrap(values,*,samples=400,seed_key=""):
 vals=tuple(float(x) for x in values)
 if not vals:return Interval(0,0,0,0)
 if samples<20:raise ValueError("bootstrap samples must be >= 20")
 seed=int(hashlib.sha256((seed_key+"|"+repr(vals)).encode()).hexdigest()[:16],16);rng=random.Random(seed)
 means=[]
 for _ in range(samples):means.append(sum(rng.choice(vals) for _ in vals)/len(vals))
 means.sort();lo=means[int(.025*(samples-1))];hi=means[int(.975*(samples-1))]
 return Interval(lo,sum(vals)/len(vals),hi,samples)
def polarity_uncertainty(observations,*,samples=400,seed_key=""):
 vals=[1.0 if x.polarity>0 else -1.0 for x in observations]
 return deterministic_bootstrap(vals,samples=samples,seed_key=seed_key)
