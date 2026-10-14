"""Learn structural historical regimes from year-indexed evidence signals."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
@dataclass(frozen=True)
class Regime:
 start_year:int;end_year:int;years:tuple[int,...];strength:float
 mean_polarity:float;mean_quality:float;mean_relevance:float
@dataclass(frozen=True)
class ChangePoint:
 year:int;score:float;polarity_shift:float;quality_shift:float;relevance_shift:float;coverage_shift:float
def _features(row):
 obs=max(1,int(row.get("observations",0)))
 polarity=(int(row.get("positive",0))-int(row.get("negative",0)))/obs
 return polarity,float(row.get("mean_source_score",0)),float(row.get("mean_relevance",0)),min(1.0,int(row.get("distinct_hosts",0))/3)
class RegimeDetector:
 def __init__(self,signals:Mapping[int,Mapping[str,object]]):self.signals={int(y):dict(v) for y,v in signals.items()}
 def change_points(self,*,threshold=.45):
  if not 0<=threshold<=4:raise ValueError("invalid change threshold")
  years=sorted(self.signals);out=[]
  for a,b in zip(years,years[1:]):
   if b-a>1:continue
   fa,fb=_features(self.signals[a]),_features(self.signals[b]);d=[abs(x-y) for x,y in zip(fa,fb)]
   score=.4*d[0]+.2*d[1]+.2*d[2]+.2*d[3]
   if score>=threshold:out.append(ChangePoint(b,score,fb[0]-fa[0],fb[1]-fa[1],fb[2]-fa[2],fb[3]-fa[3]))
  return tuple(out)
 def regimes(self,*,threshold=.45):
  years=sorted(self.signals)
  if not years:return ()
  cuts={x.year for x in self.change_points(threshold=threshold)};groups=[];current=[]
  for year in years:
   if current and (year in cuts or year-current[-1]>1):groups.append(current);current=[]
   current.append(year)
  if current:groups.append(current)
  out=[]
  for group in groups:
   rows=[_features(self.signals[y]) for y in group]
   out.append(Regime(group[0],group[-1],tuple(group),len(group)/max(1,group[-1]-group[0]+1),
    sum(x[0] for x in rows)/len(rows),sum(x[1] for x in rows)/len(rows),sum(x[2] for x in rows)/len(rows)))
  return tuple(out)
