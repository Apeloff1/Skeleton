from dataclasses import dataclass
@dataclass(frozen=True)
class DataLocation: region:str; freshness:int; classification:str
@dataclass(frozen=True)
class LocalityConstraint: allowed_regions:frozenset[str]; max_age:int
@dataclass(frozen=True)
class TransferPlan: source:DataLocation; target_region:str; cost:float; allowed:bool
def plan_transfer(source,target,c,cost):
 if target not in c.allowed_regions:return TransferPlan(source,target,cost,False)
 if source.freshness>c.max_age:return TransferPlan(source,target,cost,False)
 return TransferPlan(source,target,cost,True)
