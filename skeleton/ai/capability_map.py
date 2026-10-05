"""Canonical capability registry for VOL-113."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class CapabilityError(ValueError):pass
class Maturity(str,Enum): PLANNED="planned"; EXPERIMENTAL="experimental"; PRODUCTION="production"
class Availability(str,Enum): AVAILABLE="available"; DEGRADED="degraded"; UNAVAILABLE="unavailable"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise CapabilityError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class CapabilityDescriptor:
 capability_id:str;owner_id:str;maturity:Maturity;dependency_ids:tuple[str,...];guarantees:tuple[str,...]
 def __post_init__(self):
  object.__setattr__(self,"capability_id",_id(self.capability_id,"capability_id"));object.__setattr__(self,"owner_id",_id(self.owner_id,"owner_id"))
  if not isinstance(self.maturity,Maturity):raise CapabilityError("maturity must be Maturity")\n  if not isinstance(self.dependency_ids,tuple) or not isinstance(self.guarantees,tuple):raise CapabilityError("dependencies and guarantees must be tuples")\n  deps=tuple(_id(x,"dependency_id") for x in self.dependency_ids)\n  if len(set(deps))!=len(deps):raise CapabilityError("duplicate capability dependency")\n  deps=tuple(sorted(deps))
  if self.capability_id in deps:raise CapabilityError("self dependency")
  if not self.guarantees or any(not isinstance(x,str) or not x.strip() for x in self.guarantees):raise CapabilityError("capability guarantees required")\n  if len(set(self.guarantees))!=len(self.guarantees):raise CapabilityError("duplicate capability guarantee")
  object.__setattr__(self,"dependency_ids",deps);object.__setattr__(self,"guarantees",tuple(sorted(set(self.guarantees))))
@dataclass(frozen=True,slots=True)
class CapabilityAvailability:
 capability_id:str;state:Availability;reason:str
 def __post_init__(self):
  object.__setattr__(self,"capability_id",_id(self.capability_id,"capability_id"))
  if not isinstance(self.state,Availability):raise CapabilityError("state must be Availability")\n  if not isinstance(self.reason,str):raise CapabilityError("reason must be str")\n  if self.state is Availability.AVAILABLE and self.reason:raise CapabilityError("available capability cannot carry degradation reason")\n  if self.state is not Availability.AVAILABLE and not self.reason.strip():raise CapabilityError("degraded/unavailable capability requires reason")
class CapabilityMap:
 def __init__(self,descriptors,live):
  self.descriptors={d.capability_id:d for d in descriptors};self.live={x.capability_id:x for x in live}
  for d in self.descriptors.values():
   if any(x not in self.descriptors for x in d.dependency_ids):raise CapabilityError("unknown capability dependency")\n  self._reject_cycles()
 def _reject_cycles(self):\n  visiting=set();visited=set()\n  def visit(cid):\n   if cid in visiting:raise CapabilityError("capability dependency cycle")\n   if cid in visited:return\n   visiting.add(cid)\n   for dep in self.descriptors[cid].dependency_ids:visit(dep)\n   visiting.remove(cid);visited.add(cid)\n  for cid in sorted(self.descriptors):visit(cid)\n def resolve(self,capability_id):
  _id(capability_id,"capability_id")
  d=self.descriptors.get(capability_id)
  if d is None:raise CapabilityError("unknown capability")
  if d.maturity is Maturity.PLANNED:return CapabilityAvailability(capability_id,Availability.UNAVAILABLE,"planned_not_live")
  own=self.live.get(capability_id)
  if own is None or own.state is Availability.UNAVAILABLE:return CapabilityAvailability(capability_id,Availability.UNAVAILABLE,own.reason if own else "no_live_evidence")
  deps=[self.resolve(x) for x in d.dependency_ids]
  bad=[x for x in deps if x.state is not Availability.AVAILABLE]
  if bad:return CapabilityAvailability(capability_id,Availability.DEGRADED,"dependency:"+",".join(x.capability_id for x in bad))
  return own
 def require(self,capability_id):
  resolved=self.resolve(capability_id)
  if resolved.state is not Availability.AVAILABLE:raise CapabilityError("capability guarantee unavailable: "+resolved.reason)
  return self.descriptors[capability_id]
