"""Deterministic temporal drift, calibration, and adaptive-window authority."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError,decade_of

def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _ppm(v,n):
 if not isinstance(v,int) or isinstance(v,bool) or not 0<=v<=1_000_000: raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class ForecastObservation:
 observation_id:str; year:int; forecast_ppm:int; outcome:bool; source_digest:str
 def __post_init__(self):
  _ppm(self.forecast_ppm,"forecast"); 
  if not isinstance(self.outcome,bool): raise TemporalSignalError("outcome must be boolean")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class CalibrationReceipt:
 observation_digests:tuple[str,...]; brier_ppm:int; calibration_error_ppm:int; sample_count:int
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class DriftWindow:
 subject:str; start_year:int; end_year:int; signal_count:int; mean_support_ppm:int; previous_mean_ppm:int
 delta_ppm:int; threshold_ppm:int; drift:bool
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class ChangePointState:
 subject:str; policy_year:int; run_length_years:int; change_probability_ppm:int; last_change_year:int
 evidence_digest:str
 @property
 def digest(self): return _digest(self.__dict__)

def score_calibration(observations):
 obs=tuple(observations)
 if not obs: raise TemporalSignalError("calibration observations required")
 if len({o.observation_id for o in obs})!=len(obs): raise TemporalSignalError("duplicate calibration observation")
 squared=0
 buckets={}
 for o in obs:
  target=1_000_000 if o.outcome else 0
  squared+=(o.forecast_ppm-target)**2
  bucket=(o.forecast_ppm//100_000)*100_000
  yes,total=buckets.get(bucket,(0,0)); buckets[bucket]=(yes+(1 if o.outcome else 0),total+1)
 brier=min(1_000_000,squared//len(obs)//1_000_000)
 cal=0
 for bucket,(yes,total) in buckets.items():
  observed=(yes*1_000_000)//total
  cal+=abs(bucket-observed)*total
 cal//=len(obs)
 return CalibrationReceipt(tuple(sorted(o.digest for o in obs)),brier,cal,len(obs))

def adaptive_drift_window(year_support,*,subject,min_window=2,threshold_ppm=200_000):
 items=tuple(sorted(year_support))
 if len(items)<min_window*2: raise TemporalSignalError("insufficient drift history")
 _ppm(threshold_ppm,"drift threshold")
 best=None
 for cut in range(min_window,len(items)-min_window+1):
  left=items[:cut]; right=items[cut:]
  a=sum(v for _,v in left)//len(left); b=sum(v for _,v in right)//len(right); delta=abs(b-a)
  candidate=(delta,cut,a,b)
  if best is None or candidate>best: best=candidate
 delta,cut,a,b=best
 return DriftWindow(subject,items[cut][0],items[-1][0],len(items)-cut,b,a,delta,threshold_ppm,delta>=threshold_ppm)

def update_change_point_state(window,*,policy_year,prior=None,hazard_ppm=100_000):
 _ppm(hazard_ppm,"hazard")
 if policy_year<window.end_year: raise TemporalSignalError("policy year predates drift window")
 if window.drift:
  excess=max(0,window.delta_ppm-window.threshold_ppm)
  probability=min(1_000_000,hazard_ppm+excess)
  last=window.start_year; run=max(0,policy_year-last)
 else:
  probability=hazard_ppm
  last=prior.last_change_year if prior else window.start_year
  run=max(0,policy_year-last)
 return ChangePointState(window.subject,policy_year,run,probability,last,window.digest)

def require_calibrated_forecaster(receipt,*,max_brier_ppm=250_000,max_calibration_error_ppm=150_000):
 if receipt.brier_ppm>max_brier_ppm: raise TemporalSignalError("forecast Brier score exceeds policy")
 if receipt.calibration_error_ppm>max_calibration_error_ppm: raise TemporalSignalError("forecast calibration error exceeds policy")
 return receipt.digest

__all__=["ForecastObservation","CalibrationReceipt","DriftWindow","ChangePointState","score_calibration","adaptive_drift_window","update_change_point_state","require_calibrated_forecaster"]
