from dataclasses import dataclass
@dataclass(frozen=True)
class FreshnessRequirement:
 max_age:int; min_watermark:int; stale_action:str
@dataclass(frozen=True)
class FreshnessState:
 age:int; source_watermark:int; valid:bool
@dataclass(frozen=True)
class FreshnessDecision:
 fresh:bool; action:str
def decide_freshness(req,state):
 fresh=state.valid and state.age<=req.max_age and state.source_watermark>=req.min_watermark
 if fresh:return FreshnessDecision(True,"use")
 if req.stale_action not in {"refresh","qualify","abstain"}:raise ValueError("unsafe stale action")
 return FreshnessDecision(False,req.stale_action)
