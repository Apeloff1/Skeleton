from dataclasses import dataclass
@dataclass(frozen=True)
class ExperimentKillSwitch: enabled:bool
@dataclass(frozen=True)
class ExperimentalFeature: feature_id:str; scope:str; production_capability:bool=False
@dataclass(frozen=True)
class ExperimentExposure: feature:ExperimentalFeature; traffic:str; kill_switch:ExperimentKillSwitch; active:bool
def expose(f,traffic,kill):
 if not f.feature_id or not f.scope or not isinstance(f.production_capability,bool) or not isinstance(kill.enabled,bool):raise ValueError("valid experiment identity and controls required")
 if f.production_capability:raise PermissionError("experiment cannot satisfy production capability")
 if traffic not in {"synthetic","shadow"}:raise PermissionError("experimental traffic must be isolated")
 return ExperimentExposure(f,traffic,kill,not kill.enabled)
