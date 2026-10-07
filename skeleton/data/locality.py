from dataclasses import dataclass
import math
@dataclass(frozen=True)
class DataLocation: region:str; freshness:int; classification:str
@dataclass(frozen=True)
class LocalityConstraint: allowed_regions:frozenset[str]; max_age:int; allowed_classifications:frozenset[str]=frozenset({"public"})
@dataclass(frozen=True)
class TransferPlan: source:DataLocation; target_region:str; cost:float; allowed:bool
def plan_transfer(source,target,c,cost):
 if not source.region or not source.classification or not target:return TransferPlan(source,target,cost,False)
 if target not in c.allowed_regions or source.classification not in c.allowed_classifications:return TransferPlan(source,target,cost,False)
 if isinstance(source.freshness,bool) or source.freshness<0 or isinstance(c.max_age,bool) or c.max_age<0 or source.freshness>c.max_age:return TransferPlan(source,target,cost,False)
 if isinstance(cost,bool) or not isinstance(cost,(int,float)) or not math.isfinite(cost) or cost<0:return TransferPlan(source,target,cost,False)
 return TransferPlan(source,target,cost,True)
