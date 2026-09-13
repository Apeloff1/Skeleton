"""Immutable execution receipt for observable admission outcomes."""
from dataclasses import dataclass
@dataclass(frozen=True)
class Receipt:
 request_id:str
 decision:str
 reason:str
 def accepted(self): return self.decision=="accept"
