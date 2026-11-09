"""Temporal query constraints for evidence/retrieval filtering."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class TemporalScope:
 event_from:int|None=None;event_to:int|None=None;as_of:float|None=None
 def __post_init__(self):
  if self.event_from is not None and self.event_to is not None and self.event_from>self.event_to:raise ValueError("invalid temporal scope")
 def matches_years(self,years):
  if self.event_from is None and self.event_to is None:return True
  return any((self.event_from is None or y>=self.event_from) and (self.event_to is None or y<=self.event_to) for y in years)
def filter_temporal(observations,scope):
 return tuple(x for x in observations if scope.matches_years(x.signal_years) and (scope.as_of is None or x.fetched_at<=scope.as_of))
