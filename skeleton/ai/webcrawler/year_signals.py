"""Year-over-year signal analysis for evidence-aware research."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
@dataclass(frozen=True)
class YearSignalDelta:
 year:int;previous_year:int|None;host_delta:int;observation_delta:int
 relevance_delta:float;quality_delta:float;polarity_delta:int
class YearSignalSeries:
 def __init__(self,signals:Mapping[int,Mapping[str,object]]):self.signals={int(k):dict(v) for k,v in signals.items()}
 def deltas(self):
  out=[];previous=None
  for year in sorted(self.signals):
   cur=self.signals[year];old=self.signals.get(previous,{}) if previous is not None else {}
   out.append(YearSignalDelta(year,previous,
    int(cur.get("distinct_hosts",0))-int(old.get("distinct_hosts",0)),
    int(cur.get("observations",0))-int(old.get("observations",0)),
    float(cur.get("mean_relevance",0))-float(old.get("mean_relevance",0)),
    float(cur.get("mean_source_score",0))-float(old.get("mean_source_score",0)),
    (int(cur.get("positive",0))-int(cur.get("negative",0)))-(int(old.get("positive",0))-int(old.get("negative",0)))))
   previous=year
  return tuple(out)
 def strongest_years(self,limit=5):
  if limit<1:raise ValueError("limit must be positive")
  return tuple(sorted(self.signals,key=lambda y:(-int(self.signals[y].get("distinct_hosts",0)),-int(self.signals[y].get("observations",0)),y))[:limit])
