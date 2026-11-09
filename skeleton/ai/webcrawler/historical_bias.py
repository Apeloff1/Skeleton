"""Historical evidence bias diagnostics across years and decades."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
@dataclass(frozen=True)
class HistoricalBias:
 bucket:int;coverage:float;concentration:float;quality:float;risk:float;reasons:tuple[str,...]
class HistoricalBiasAnalyzer:
 def analyze(self,signals:Mapping[int,Mapping[str,object]],*,bucket_size=10):
  if bucket_size<1:raise ValueError("bucket_size must be positive")
  groups={}
  for year,row in signals.items():groups.setdefault((int(year)//bucket_size)*bucket_size,[]).append((int(year),row))
  out=[]
  for bucket,rows in sorted(groups.items()):
   coverage=len({y for y,_ in rows})/bucket_size;obs=sum(int(r.get("observations",0)) for _,r in rows)
   hosts=sum(int(r.get("distinct_hosts",0)) for _,r in rows)
   concentration=1.0-min(1.0,hosts/max(1,obs))
   quality=sum(float(r.get("mean_source_score",0))*int(r.get("observations",0)) for _,r in rows)/max(1,obs)
   risk=max(0.0,min(1.0,.45*(1-coverage)+.35*concentration+.20*(1-quality)))
   reasons=[]
   if coverage<.5:reasons.append("sparse-year-coverage")
   if concentration>.5:reasons.append("source-concentration")
   if quality<.5:reasons.append("low-source-quality")
   out.append(HistoricalBias(bucket,coverage,concentration,quality,risk,tuple(reasons)))
  return tuple(out)
