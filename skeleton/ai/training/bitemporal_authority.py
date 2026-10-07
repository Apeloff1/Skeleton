"""Bitemporal truth: valid-time and knowledge-time are separate authority axes."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class BitemporalFact:
 fact_id:str; subject:str; relation:str; object_digest:str
 valid_from_year:int; valid_through_year:int; known_from_year:int; known_through_year:int
 source_digest:str
 def __post_init__(self):
  _hex(self.object_digest,"object"); _hex(self.source_digest,"source")
  if self.valid_from_year>self.valid_through_year: raise TemporalSignalError("invalid valid-time interval")
  if self.known_from_year>self.known_through_year: raise TemporalSignalError("invalid knowledge-time interval")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class BitemporalSnapshot:
 world_year:int; knowledge_year:int; fact_digests:tuple[str,...]; excluded_unknown:int; excluded_invalid:int
 @property
 def digest(self): return _digest(self.__dict__)

def bitemporal_snapshot(facts,*,world_year,knowledge_year):
 facts=tuple(facts)
 if len({f.fact_id for f in facts})!=len(facts): raise TemporalSignalError("duplicate bitemporal fact")
 visible=[]; unknown=invalid=0
 for f in facts:
  known=f.known_from_year<=knowledge_year<=f.known_through_year
  valid=f.valid_from_year<=world_year<=f.valid_through_year
  if not known: unknown+=1
  elif not valid: invalid+=1
  else: visible.append(f.digest)
 return BitemporalSnapshot(world_year,knowledge_year,tuple(sorted(visible)),unknown,invalid)

def require_no_future_knowledge(snapshot):
 if snapshot.knowledge_year<snapshot.world_year:
  return snapshot.digest
 if snapshot.knowledge_year==snapshot.world_year:
  return snapshot.digest
 raise TemporalSignalError("knowledge snapshot exceeds requested world-time boundary")

__all__=["BitemporalFact","BitemporalSnapshot","bitemporal_snapshot","require_no_future_knowledge"]
