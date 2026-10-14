"""Detect precursor/lag relationships between annual research signal series."""
from __future__ import annotations
from dataclasses import dataclass
import math
@dataclass(frozen=True)
class LagSignal:
 lag_years:int;correlation:float;overlap:int
def _pearson(a,b):
 if len(a)<3:return 0.0
 ma=sum(a)/len(a);mb=sum(b)/len(b);da=[x-ma for x in a];db=[x-mb for x in b]
 den=math.sqrt(sum(x*x for x in da)*sum(x*x for x in db))
 return 0.0 if den==0 else sum(x*y for x,y in zip(da,db))/den
def lag_scan(left,right,*,max_lag=5,field="net_polarity"):
 if max_lag<0:raise ValueError("max_lag must be non-negative")
 def val(row):
  if field=="net_polarity":return float(row.get("positive",0))-float(row.get("negative",0))
  return float(row.get(field,0))
 out=[]
 for lag in range(-max_lag,max_lag+1):
  pairs=[(float(left[y].get(field,0)) if field!="net_polarity" else val(left[y]),val(right[y+lag])) for y in left if y+lag in right]
  if len(pairs)>=3:out.append(LagSignal(lag,_pearson([x for x,_ in pairs],[y for _,y in pairs]),len(pairs)))
 return tuple(sorted(out,key=lambda x:(-abs(x.correlation),-x.overlap,abs(x.lag_years),x.lag_years)))
