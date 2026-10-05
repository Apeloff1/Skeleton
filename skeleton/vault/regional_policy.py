"""Deterministic regional privacy-policy mapping."""
from dataclasses import dataclass
from .erasure_topology import ErasureTopologyError
@dataclass(frozen=True,slots=True)
class RegionalPrivacyPolicy:
 region:str;allowed_purposes:tuple[str,...];allowed_transfer_regions:tuple[str,...];export_allowed:bool;deletion_required:bool;max_retention_days:int|None=None
 def __post_init__(self):
  if not isinstance(self.region,str) or not self.region or self.region!=self.region.strip():raise ErasureTopologyError("invalid region")
  if not isinstance(self.allowed_purposes,tuple) or not self.allowed_purposes:raise ErasureTopologyError("purposes required")
  if not isinstance(self.allowed_transfer_regions,tuple):raise ErasureTopologyError("transfer regions must be tuple")
  object.__setattr__(self,"allowed_purposes",tuple(sorted(set(self.allowed_purposes))))
  object.__setattr__(self,"allowed_transfer_regions",tuple(sorted(set(x.upper() for x in self.allowed_transfer_regions))))
  if self.max_retention_days is not None and (isinstance(self.max_retention_days,bool) or not isinstance(self.max_retention_days,int) or self.max_retention_days<0):raise ErasureTopologyError("invalid retention bound")
class RegionalPolicyMap:
 def __init__(self,policies:tuple[RegionalPrivacyPolicy,...]):
  if not isinstance(policies,tuple) or not policies:raise ErasureTopologyError("policies required")
  by={p.region.upper():p for p in policies}
  if len(by)!=len(policies):raise ErasureTopologyError("duplicate region")
  self._by=by
 def require(self,region:str,purpose:str,*,export:bool=False,transfer_region:str|None=None,retention_days:int|None=None)->RegionalPrivacyPolicy:
  if not isinstance(region,str) or region.upper() not in self._by:raise ErasureTopologyError("unknown region")
  policy=self._by[region.upper()]
  if purpose not in policy.allowed_purposes:raise ErasureTopologyError("purpose denied by regional policy")
  if export and not policy.export_allowed:raise ErasureTopologyError("export denied by regional policy")
  if transfer_region is not None and transfer_region.upper() not in policy.allowed_transfer_regions:raise ErasureTopologyError("regional transfer denied")
  if retention_days is not None and policy.max_retention_days is not None and retention_days>policy.max_retention_days:raise ErasureTopologyError("regional retention bound exceeded")
  return policy
