"""Regime-transfer invariants for temporal evidence authority."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class RegimeObservation:
 regime_id:str; subject:str; mechanism_digest:str; support_ppm:int; sample_digest:str
 def __post_init__(self):
  _hex(self.mechanism_digest,"mechanism"); _hex(self.sample_digest,"sample")
  if not 0<=self.support_ppm<=1_000_000: raise TemporalSignalError("invalid regime support")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class InvarianceReceipt:
 subject:str; observation_digests:tuple[str,...]; regime_count:int; mechanism_count:int
 support_floor_ppm:int; invariant:bool
 @property
 def digest(self): return _digest(self.__dict__)

def assess_regime_invariance(observations,*,minimum_regimes=2,min_support_ppm=700_000):
 obs=tuple(observations)
 if len({o.regime_id for o in obs})<minimum_regimes: raise TemporalSignalError("insufficient independent regimes")
 subjects={o.subject for o in obs}
 if len(subjects)!=1: raise TemporalSignalError("cross-subject invariance contamination")
 mechanisms={o.mechanism_digest for o in obs}; floor=min(o.support_ppm for o in obs)
 return InvarianceReceipt(next(iter(subjects)),tuple(sorted(o.digest for o in obs)),len({o.regime_id for o in obs}),len(mechanisms),floor,len(mechanisms)==1 and floor>=min_support_ppm)

def require_regime_invariance(receipt):
 if not receipt.invariant: raise TemporalSignalError("mechanism does not transfer invariantly across regimes")
 return receipt.digest
__all__=["RegimeObservation","InvarianceReceipt","assess_regime_invariance","require_regime_invariance"]
