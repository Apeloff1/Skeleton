from dataclasses import dataclass
@dataclass(frozen=True)
class ToolProbe: probe_id:str; side_effect_free:bool; observed_at:int
@dataclass(frozen=True)
class ToolHealthState: transport_ok:bool; semantic_ok:bool; auth_ok:bool; quota_ok:bool
@dataclass(frozen=True)
class ToolHealth: probe:ToolProbe; state:ToolHealthState
def authorize_risky(h,now,max_age):
 if not h.probe.side_effect_free:raise ValueError("unsafe health probe")
 return now-h.probe.observed_at<=max_age and all((h.state.transport_ok,h.state.semantic_ok,h.state.auth_ok,h.state.quota_ok))
