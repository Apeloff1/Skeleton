"""Isolate hypothetical timelines from observed temporal evidence."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()

@dataclass(frozen=True)
class CounterfactualBranch:
 branch_id:str; parent_snapshot_digest:str; intervention_digest:str; fork_year:int; branch_kind:str="counterfactual"
 def __post_init__(self):
  if self.branch_kind!="counterfactual": raise TemporalSignalError("hypothetical branch must be counterfactual")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class CounterfactualOutcome:
 branch_digest:str; outcome_digest:str; year:int; probability_ppm:int
 def __post_init__(self):
  if not 0<=self.probability_ppm<=1_000_000: raise TemporalSignalError("invalid counterfactual probability")
 @property
 def digest(self): return _digest(self.__dict__)

def require_observed_evidence_not_counterfactual(*,evidence_branch_digest=None):
 if evidence_branch_digest is not None: raise TemporalSignalError("counterfactual evidence cannot authorize observed-world promotion")
 return True

def validate_counterfactual_outcome(branch,outcome):
 if outcome.branch_digest!=branch.digest: raise TemporalSignalError("counterfactual branch mismatch")
 if outcome.year<branch.fork_year: raise TemporalSignalError("counterfactual outcome predates intervention")
 return outcome.digest

__all__=["CounterfactualBranch","CounterfactualOutcome","require_observed_evidence_not_counterfactual","validate_counterfactual_outcome"]
