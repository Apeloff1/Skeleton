"""Classify how evidence signals evolve across learned historical regimes."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class RegimeTransition:
 previous_start:int|None;current_start:int;label:str;polarity_delta:float;quality_delta:float
def classify_regime_transitions(regimes):
 out=[];prev=None
 for cur in regimes:
  if prev is None:label="emerging"
  else:
   pd=cur.mean_polarity-prev.mean_polarity;qd=cur.mean_quality-prev.mean_quality
   if prev.mean_polarity*cur.mean_polarity<0 and abs(pd)>=.5:label="reversed"
   elif abs(pd)<.15 and abs(qd)<.15:label="stable"
   elif pd>.25:label="strengthening"
   elif pd<-.25:label="weakening"
   else:label="transitioning"
   if len(out)>=2 and label=="strengthening":
    older=regimes[len(out)-2]
    if older.mean_polarity>cur.mean_polarity-.15 and prev.mean_polarity<older.mean_polarity-.25:label="rediscovered"
  out.append(RegimeTransition(prev.start_year if prev else None,cur.start_year,label,
   cur.mean_polarity-(prev.mean_polarity if prev else 0),cur.mean_quality-(prev.mean_quality if prev else 0)))
  prev=cur
 return tuple(out)
