"""Explicit network zones/routes/failure semantics for VOL-171."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class NetworkError(ValueError):pass
class ZoneKind(str,Enum): PUBLIC="public";INGRESS="ingress";CONTROL="control";DATA="data";EGRESS="egress"
class PartitionMode(str,Enum): FAIL_CLOSED="fail_closed";READ_ONLY="read_only"
@dataclass(frozen=True,slots=True)
class NetworkZone:
 zone_id:str;kind:ZoneKind
 def __post_init__(self):
  if not _ID.fullmatch(self.zone_id):raise NetworkError("invalid zone")
@dataclass(frozen=True,slots=True)
class NetworkRoute:
 route_id:str;source_zone:str;target_zone:str;dns_policy:str;timeout_ms:int;max_retries:int;proxy_required:bool;partition_mode:PartitionMode
 def __post_init__(self):
  if not _ID.fullmatch(self.route_id) or self.timeout_ms<1 or not 0<=self.max_retries<=5 or not self.dns_policy:raise NetworkError("invalid route")
@dataclass(frozen=True,slots=True)
class NetworkPolicy:
 zones:tuple[NetworkZone,...];routes:tuple[NetworkRoute,...]
 def __post_init__(self):
  z={x.zone_id:x for x in self.zones}
  if len(z)!=len(self.zones):raise NetworkError("duplicate zone")
  for r in self.routes:
   if r.source_zone not in z or r.target_zone not in z:raise NetworkError("unknown route zone")
   s,t=z[r.source_zone].kind,z[r.target_zone].kind
   if s is ZoneKind.PUBLIC and t in {ZoneKind.CONTROL,ZoneKind.DATA}:raise NetworkError("public path bypasses ingress")
   if s is ZoneKind.INGRESS and t is ZoneKind.EGRESS:raise NetworkError("ingress cannot bypass internal policy")
 def route(self,source,target):
  found=[r for r in self.routes if r.source_zone==source and r.target_zone==target]
  if len(found)!=1:raise NetworkError("route absent or ambiguous")
  return found[0]
