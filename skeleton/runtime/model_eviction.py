from dataclasses import dataclass
@dataclass(frozen=True)
class DrainState:
 in_flight:int; pinned:bool
 def __post_init__(self):
  if isinstance(self.in_flight,bool) or not isinstance(self.in_flight,int) or self.in_flight<0 or not isinstance(self.pinned,bool):raise ValueError("invalid drain state")
@dataclass(frozen=True)
class EvictionPolicy:
 min_idle:int; allow_reload:bool=True
 def __post_init__(self):
  if isinstance(self.min_idle,bool) or not isinstance(self.min_idle,int) or self.min_idle<0 or not isinstance(self.allow_reload,bool):raise ValueError("invalid eviction policy")
@dataclass(frozen=True)
class ModelEviction: model_id:str; reason:str; reloadable:bool
def evict(model_id,state,policy,idle):
 if not model_id or isinstance(idle,bool) or not isinstance(idle,int) or idle<0:raise ValueError("valid model and idle duration required")
 if state.pinned or state.in_flight:raise PermissionError("model not at safe eviction boundary")
 if idle<policy.min_idle:raise PermissionError("eviction would thrash")
 return ModelEviction(model_id,"idle-pressure",policy.allow_reload)
