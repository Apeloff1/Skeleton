"""Validity-aware temporal facts and leakage-safe historical snapshots."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError

def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalFact:
 fact_id:str; subject:str; relation:str; object_digest:str; valid_from_year:int; valid_through_year:int
 observed_year:int; source_digest:str; supersedes_digest:str|None=None
 def __post_init__(self):
  if not self.fact_id or not self.subject or not self.relation: raise TemporalSignalError("temporal fact identity required")
  _hex(self.object_digest,"object"); _hex(self.source_digest,"source")
  if self.supersedes_digest is not None: _hex(self.supersedes_digest,"supersedes")
  for year in (self.valid_from_year,self.valid_through_year,self.observed_year):
   if isinstance(year,bool) or not isinstance(year,int) or not 1900<=year<=2200: raise TemporalSignalError("invalid temporal fact year")
  if self.valid_through_year<self.valid_from_year: raise TemporalSignalError("invalid fact validity interval")
  if self.observed_year<self.valid_from_year: raise TemporalSignalError("fact observed before validity")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class TemporalSnapshot:
 as_of_year:int; fact_digests:tuple[str,...]; excluded_future_count:int; superseded_count:int
 @property
 def digest(self): return _digest(self.__dict__)

def snapshot_facts(facts,*,as_of_year):
 facts=tuple(facts)
 if isinstance(as_of_year,bool) or not isinstance(as_of_year,int) or not 1900<=as_of_year<=2200: raise TemporalSignalError("invalid snapshot year")
 if any(not isinstance(f,TemporalFact) for f in facts): raise TemporalSignalError("TemporalFact required")
 if len({f.fact_id for f in facts})!=len(facts): raise TemporalSignalError("duplicate temporal fact id")
 visible=[]; future=0
 for f in facts:
  if f.observed_year>as_of_year: future+=1; continue
  if f.valid_from_year<=as_of_year<=f.valid_through_year: visible.append(f)
 digests={f.digest for f in visible}; superseded={f.supersedes_digest for f in visible if f.supersedes_digest in digests}
 active=tuple(sorted(f.digest for f in visible if f.digest not in superseded))
 return TemporalSnapshot(as_of_year,active,future,len(superseded))

def require_historical_snapshot(snapshot,*,expected_year):
 if snapshot.as_of_year!=expected_year: raise TemporalSignalError("historical snapshot year mismatch")
 if snapshot.excluded_future_count<0: raise TemporalSignalError("invalid future exclusion count")
 return snapshot.digest

__all__=["TemporalFact","TemporalSnapshot","snapshot_facts","require_historical_snapshot"]
