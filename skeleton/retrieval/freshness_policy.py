from dataclasses import dataclass
@dataclass(frozen=True)
class FreshnessRequirement:
 max_age:int; min_watermark:int; stale_action:str
 def __post_init__(self):
  if any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in (self.max_age,self.min_watermark)):raise ValueError("nonnegative freshness bounds required")
  if self.stale_action not in {"refresh","qualify","abstain"}:raise ValueError("unsafe stale action")
@dataclass(frozen=True)
class FreshnessState:
 age:int; source_watermark:int; valid:bool
 def __post_init__(self):
  if any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in (self.age,self.source_watermark)) or not isinstance(self.valid,bool):raise ValueError("invalid freshness state")
@dataclass(frozen=True)
class FreshnessDecision: fresh:bool; action:str
def decide_freshness(req,state):
 fresh=state.valid and state.age<=req.max_age and state.source_watermark>=req.min_watermark
 return FreshnessDecision(True,"use") if fresh else FreshnessDecision(False,req.stale_action)
