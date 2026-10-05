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

class ErasureTopology:
 def __init__(self,stores:tuple[DerivedStore,...]):
  if not isinstance(stores,tuple) or not stores:raise ErasureTopologyError("stores required")
  by={s.store_id:s for s in stores}
  if len(by)!=len(stores):raise ErasureTopologyError("duplicate store")
  for s in stores:
   if any(p not in by for p in s.parents):raise ErasureTopologyError("unknown parent")
  self.stores=tuple(sorted(stores,key=lambda s:s.store_id));self._by=by
  for root in by:self._walk(root,set(),set())
 def _walk(self,node,visiting,done):
  if node in visiting:raise ErasureTopologyError("derivation cycle")
  if node in done:return
  visiting.add(node)
  for p in self._by[node].parents:self._walk(p,visiting,done)
  visiting.remove(node);done.add(node)
 def targets_for(self,source:str)->tuple[str,...]:
  if source not in self._by:raise ErasureTopologyError("unknown source")
  reached={source};changed=True
  while changed:
   changed=False
   for s in self.stores:
    if s.store_id not in reached and any(p in reached for p in s.parents):reached.add(s.store_id);changed=True
  return tuple(sorted({s.deletion_target for s in self.stores if s.store_id in reached}))
 def require_coverage(self,source:str,declared:tuple[str,...])->None:
  if not isinstance(declared,tuple):raise ErasureTopologyError("declared targets must be tuple")
  missing=set(self.targets_for(source))-set(declared)
  if missing:raise ErasureTopologyError("derived deletion coverage incomplete")
