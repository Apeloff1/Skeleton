"""Multi-detector temporal drift ensemble with fail-closed disagreement."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError

def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _ppm(v,n):
 if not isinstance(v,int) or isinstance(v,bool) or not 0<=v<=1_000_000: raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class DriftDetectorVote:
 detector_id:str; detector_family:str; evidence_digest:str; drift_probability_ppm:int; window_start_year:int
 def __post_init__(self):
  if self.detector_family not in {"adaptive-window","distribution","performance","change-point"}: raise TemporalSignalError("unknown drift detector family")
  _ppm(self.drift_probability_ppm,"drift probability")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class DriftEnsembleReceipt:
 vote_digests:tuple[str,...]; family_count:int; median_probability_ppm:int; spread_ppm:int
 high_drift:bool; disagreement:bool
 @property
 def digest(self): return _digest(self.__dict__)

def combine_drift_votes(votes,*,high_threshold_ppm=700_000,max_spread_ppm=400_000,min_families=2):
 votes=tuple(votes)
 if len(votes)<2: raise TemporalSignalError("multiple drift votes required")
 if len({v.detector_id for v in votes})!=len(votes): raise TemporalSignalError("duplicate drift detector")
 families={v.detector_family for v in votes}
 if len(families)<min_families: raise TemporalSignalError("insufficient drift detector diversity")
 values=sorted(v.drift_probability_ppm for v in votes); median=values[len(values)//2]
 spread=values[-1]-values[0]
 return DriftEnsembleReceipt(tuple(sorted(v.digest for v in votes)),len(families),median,spread,median>=high_threshold_ppm,spread>max_spread_ppm)

def require_stable_drift_ensemble(receipt):
 if receipt.disagreement: raise TemporalSignalError("drift detectors materially disagree")
 if receipt.high_drift: raise TemporalSignalError("drift ensemble indicates unstable regime")
 return receipt.digest

__all__=["DriftDetectorVote","DriftEnsembleReceipt","combine_drift_votes","require_stable_drift_ensemble"]
