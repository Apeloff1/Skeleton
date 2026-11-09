"""Decade/regime aggregation over year-indexed research signals."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
@dataclass(frozen=True)
class DecadeSignalDelta:
 decade:int;previous_decade:int|None;coverage_delta:float;host_delta:int
 observation_delta:int;relevance_delta:float;quality_delta:float;polarity_delta:int
class DecadeSignalSeries:
 def __init__(self,year_signals:Mapping[int,Mapping[str,object]]):
  self.years={int(y):dict(v) for y,v in year_signals.items()}
 def aggregate(self):
  groups={}
  for year,row in self.years.items():groups.setdefault((year//10)*10,[]).append((year,row))
  out={}
  for decade,rows in sorted(groups.items()):
   years={y for y,_ in rows};obs=sum(int(r.get("observations",0)) for _,r in rows)
   host_years=sum(int(r.get("distinct_hosts",0)) for _,r in rows)
   weighted=max(1,obs)
   rel=sum(float(r.get("mean_relevance",0))*int(r.get("observations",0)) for _,r in rows)/weighted
   quality=sum(float(r.get("mean_source_score",0))*int(r.get("observations",0)) for _,r in rows)/weighted
   pos=sum(int(r.get("positive",0)) for _,r in rows);neg=sum(int(r.get("negative",0)) for _,r in rows)
   out[decade]={"years_observed":len(years),"coverage":len(years)/10.0,"observations":obs,
    "host_years":host_years,"mean_relevance":rel,"mean_source_score":quality,
    "positive":pos,"negative":neg,"net_polarity":pos-neg}
  return out
 def deltas(self):
  agg=self.aggregate();out=[];previous=None
  for decade in sorted(agg):
   cur=agg[decade];old=agg.get(previous,{}) if previous is not None else {}
   out.append(DecadeSignalDelta(decade,previous,float(cur["coverage"])-float(old.get("coverage",0)),
    int(cur["host_years"])-int(old.get("host_years",0)),int(cur["observations"])-int(old.get("observations",0)),
    float(cur["mean_relevance"])-float(old.get("mean_relevance",0)),
    float(cur["mean_source_score"])-float(old.get("mean_source_score",0)),
    int(cur["net_polarity"])-int(old.get("net_polarity",0))))
   previous=decade
  return tuple(out)
 def undercovered_decades(self,start_decade:int,end_decade:int,*,minimum_coverage=.5):
  if start_decade%10 or end_decade%10 or start_decade>end_decade or not 0<=minimum_coverage<=1:raise ValueError("invalid decade coverage request")
  agg=self.aggregate()
  return tuple(d for d in range(start_decade,end_decade+1,10) if float(agg.get(d,{}).get("coverage",0))<minimum_coverage)
