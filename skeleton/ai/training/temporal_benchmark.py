"""Temporal competence benchmark receipts for evolving knowledge."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n,*,commit=False):
 if not isinstance(v,str) or len(v) not in ((40,64) if commit else (64,)) or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")
def _ppm(v,n):
 if not isinstance(v,int) or isinstance(v,bool) or not 0<=v<=1_000_000: raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalCompetence:
 cognition_ppm:int; awareness_ppm:int; trustworthiness_ppm:int; historical_recall_ppm:int
 stale_resistance_ppm:int; edit_consistency_ppm:int
 def __post_init__(self):
  for n in self.__dataclass_fields__: _ppm(getattr(self,n),n)
 @property
 def floor_ppm(self): return min(getattr(self,n) for n in self.__dataclass_fields__)
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class TemporalBenchmarkReceipt:
 exact_head_commit:str; suite_digest:str; competence_digest:str; floor_ppm:int; passed:bool
 def __post_init__(self):
  _hex(self.exact_head_commit,"exact head",commit=True); _hex(self.suite_digest,"suite"); _hex(self.competence_digest,"competence")
  _ppm(self.floor_ppm,"competence floor")
  if not isinstance(self.passed,bool): raise TemporalSignalError("benchmark passed must be boolean")
 @property
 def digest(self): return _digest(self.__dict__)

def evaluate_temporal_competence(*,exact_head_commit,suite_digest,metrics,min_floor_ppm=700_000):
 _hex(exact_head_commit,"exact head",commit=True); _hex(suite_digest,"suite")
 _ppm(min_floor_ppm,"minimum competence floor")
 if not isinstance(metrics,TemporalCompetence): raise TemporalSignalError("TemporalCompetence required")
 floor=metrics.floor_ppm
 return TemporalBenchmarkReceipt(exact_head_commit,suite_digest,metrics.digest,floor,floor>=min_floor_ppm)

def require_temporal_benchmark(receipt):
 if not receipt.passed: raise TemporalSignalError("temporal competence benchmark failed")
 return receipt.digest

__all__=["TemporalCompetence","TemporalBenchmarkReceipt","evaluate_temporal_competence","require_temporal_benchmark"]
