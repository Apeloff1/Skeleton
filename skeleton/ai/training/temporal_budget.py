"""Resource and cardinality budgets for temporal evidence planes."""
from __future__ import annotations
from dataclasses import dataclass
from itertools import islice
from .temporal_signals import TemporalSignalError

@dataclass(frozen=True)
class TemporalBudget:
 max_signals:int=10000; max_facts:int=10000; max_sources:int=4096; max_year_span:int=200; max_decades:int=20
 def __post_init__(self):
  for n in ("max_signals","max_facts","max_sources","max_year_span","max_decades"):
   v=getattr(self,n)
   if not isinstance(v,int) or isinstance(v,bool) or v<1: raise TemporalSignalError(f"invalid {n}")

def enforce_signal_budget(signals,budget=TemporalBudget()):
 if not isinstance(budget,TemporalBudget): raise TemporalSignalError("TemporalBudget required")
 signals=tuple(islice(signals,budget.max_signals+1))
 if len(signals)>budget.max_signals: raise TemporalSignalError("temporal signal budget exceeded")
 if signals:
  if any(not isinstance(s.event_year,int) or isinstance(s.event_year,bool) or not 1900<=s.event_year<=2200 or not isinstance(s.source_digest,str) or len(s.source_digest)!=64 or any(c not in "0123456789abcdef" for c in s.source_digest) for s in signals): raise TemporalSignalError("invalid temporal signal")
  years=[s.event_year for s in signals]
  if max(years)-min(years)>budget.max_year_span: raise TemporalSignalError("temporal year span exceeded")
  if len({s.source_digest for s in signals})>budget.max_sources: raise TemporalSignalError("temporal source budget exceeded")
  if len({(y//10)*10 for y in years})>budget.max_decades: raise TemporalSignalError("temporal decade budget exceeded")
 return signals

def enforce_fact_budget(facts,budget=TemporalBudget()):
 if not isinstance(budget,TemporalBudget): raise TemporalSignalError("TemporalBudget required")
 facts=tuple(islice(facts,budget.max_facts+1))
 if len(facts)>budget.max_facts: raise TemporalSignalError("temporal fact budget exceeded")
 if any(not isinstance(f.source_digest,str) or len(f.source_digest)!=64 or any(c not in "0123456789abcdef" for c in f.source_digest) for f in facts): raise TemporalSignalError("invalid temporal fact source")
 if len({f.source_digest for f in facts})>budget.max_sources: raise TemporalSignalError("temporal fact source budget exceeded")
 return facts

__all__=["TemporalBudget","enforce_signal_budget","enforce_fact_budget"]
