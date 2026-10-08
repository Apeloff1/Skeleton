"""Distribution-free temporal uncertainty sets with rolling calibration."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _ppm(v,n):
 if not isinstance(v,int) or isinstance(v,bool) or not 0<=v<=1_000_000: raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class ResidualObservation:
 observation_id:str; year:int; absolute_error_ppm:int
 def __post_init__(self): _ppm(self.absolute_error_ppm,"absolute error")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class TemporalUncertaintyReceipt:
 calibration_digests:tuple[str,...]; target_coverage_ppm:int; radius_ppm:int; calibration_start_year:int
 calibration_end_year:int; sample_count:int
 @property
 def digest(self): return _digest(self.__dict__)

def rolling_uncertainty_set(observations,*,target_coverage_ppm=900_000,max_window=256):
 obs=tuple(sorted(observations,key=lambda x:(x.year,x.observation_id)))
 _ppm(target_coverage_ppm,"target coverage")
 if not obs: raise TemporalSignalError("uncertainty calibration required")
 if len({o.observation_id for o in obs})!=len(obs): raise TemporalSignalError("duplicate residual observation")
 obs=obs[-max_window:]; errors=sorted(o.absolute_error_ppm for o in obs)
 rank=max(0,min(len(errors)-1,((target_coverage_ppm*len(errors)+999999)//1000000)-1))
 return TemporalUncertaintyReceipt(tuple(sorted(o.digest for o in obs)),target_coverage_ppm,errors[rank],obs[0].year,obs[-1].year,len(obs))

def require_bounded_uncertainty(receipt,*,max_radius_ppm=250_000,min_samples=20):
 if receipt.sample_count<min_samples: raise TemporalSignalError("insufficient uncertainty calibration samples")
 if receipt.radius_ppm>max_radius_ppm: raise TemporalSignalError("temporal uncertainty radius exceeds policy")
 return receipt.digest

__all__=["ResidualObservation","TemporalUncertaintyReceipt","rolling_uncertainty_set","require_bounded_uncertainty"]
