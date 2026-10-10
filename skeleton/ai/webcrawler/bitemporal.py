"""Bitemporal facts: valid-time is separate from knowledge/transaction-time."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class BitemporalFact:
 valid_from:int|None;valid_to:int|None;known_from:float;known_to:float|None=None
 def valid_at(self,year:int)->bool:return (self.valid_from is None or year>=self.valid_from) and (self.valid_to is None or year<=self.valid_to)
 def known_at(self,ts:float)->bool:return ts>=self.known_from and (self.known_to is None or ts<self.known_to)
 def visible(self,*,year:int,as_of:float)->bool:return self.valid_at(year) and self.known_at(as_of)
