"""Immutable derived-store topology for governed privacy state."""
from dataclasses import dataclass
class ErasureTopologyError(ValueError):pass
def _name(v,field):
 if not isinstance(v,str) or not v or v!=v.strip() or len(v)>256:raise ErasureTopologyError("invalid "+field)
 return v
@dataclass(frozen=True,slots=True)
class DerivedStore:
 store_id:str
 parents:tuple[str,...]
 deletion_target:str
 def __post_init__(self):
  _name(self.store_id,"store_id");_name(self.deletion_target,"deletion_target")
  if not isinstance(self.parents,tuple):raise ErasureTopologyError("parents must be tuple")
  for p in self.parents:_name(p,"parent")
  if self.store_id in self.parents:raise ErasureTopologyError("self derivation")
  object.__setattr__(self,"parents",tuple(sorted(set(self.parents))))
