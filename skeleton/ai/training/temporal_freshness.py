"""Freshness and supersession policy for mixed-current/outdated retrieval corpora."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()

@dataclass(frozen=True)
class FactVersion:
 version_id:str; logical_key:str; fact_digest:str; observed_year:int; valid_from_year:int; valid_through_year:int; source_digest:str
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class FreshnessResolution:
 logical_key:str; policy_year:int; selected_digest:str; rejected_digests:tuple[str,...]; ambiguity:bool
 @property
 def digest(self): return _digest(self.__dict__)

def resolve_fact_versions(versions,*,policy_year):
 versions=tuple(versions)
 if not versions: raise TemporalSignalError("fact versions required")
 key=versions[0].logical_key
 if any(v.logical_key!=key for v in versions): raise TemporalSignalError("mixed logical fact keys")
 observable=[v for v in versions if v.observed_year<=policy_year and v.valid_from_year<=policy_year<=v.valid_through_year]
 if not observable: raise TemporalSignalError("no valid observable fact version")
 newest=max(v.observed_year for v in observable); candidates=[v for v in observable if v.observed_year==newest]
 unique={v.fact_digest for v in candidates}
 if len(unique)!=1: raise TemporalSignalError("freshest fact versions conflict")
 selected=sorted(candidates,key=lambda v:v.digest)[0]
 rejected=tuple(sorted(v.digest for v in versions if v.digest!=selected.digest))
 return FreshnessResolution(key,policy_year,selected.digest,rejected,False)

__all__=["FactVersion","FreshnessResolution","resolve_fact_versions"]
