"""Deterministic interval algebra for temporal facts and claims."""
from __future__ import annotations
from dataclasses import dataclass
from .temporal_signals import TemporalSignalError
@dataclass(frozen=True)
class YearInterval:
 start:int; end:int
 def __post_init__(self):
  if self.start>self.end: raise TemporalSignalError("invalid interval")
 def relation(self,other):
  if self.end<other.start:return "before"
  if self.start>other.end:return "after"
  if self.start==other.start and self.end==other.end:return "equal"
  if self.start<=other.start and self.end>=other.end:return "contains"
  if other.start<=self.start and other.end>=self.end:return "during"
  if self.end==other.start:return "meets"
  if self.start==other.end:return "met-by"
  return "overlaps"
 def intersection(self,other):
  a=max(self.start,other.start); b=min(self.end,other.end)
  return None if a>b else YearInterval(a,b)

def require_temporal_compatibility(a,b,*,allowed=("equal","contains","during","overlaps","meets","met-by")):
 r=a.relation(b)
 if r not in allowed: raise TemporalSignalError(f"temporally incompatible intervals: {r}")
 return r
__all__=["YearInterval","require_temporal_compatibility"]
