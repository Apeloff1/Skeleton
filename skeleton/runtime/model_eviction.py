from dataclasses import dataclass
@dataclass(frozen=True)
class DrainState: in_flight:int; pinned:bool
@dataclass(frozen=True)
class EvictionPolicy: min_idle:int; allow_reload:bool=True
@dataclass(frozen=True)
class ModelEviction: model_id:str; reason:str; reloadable:bool
def evict(model_id,state,policy,idle):
 if state.pinned or state.in_flight:raise PermissionError("model not at safe eviction boundary")
 if idle<policy.min_idle:raise PermissionError("eviction would thrash")
 return ModelEviction(model_id,"idle-pressure",policy.allow_reload)
