"""Bounded long-horizon benchmark contracts for VOL-218."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class LongHorizonBenchmarkError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise LongHorizonBenchmarkError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise LongHorizonBenchmarkError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class HorizonCheckpoint:
    step:int; state_digest:str; invariant_digest:str; progress_ppm:int
    def __post_init__(self):
        if isinstance(self.step,bool) or not isinstance(self.step,int) or self.step<0: raise LongHorizonBenchmarkError("step must be non-negative")
        object.__setattr__(self,"state_digest",_sha("state_digest",self.state_digest)); object.__setattr__(self,"invariant_digest",_sha("invariant_digest",self.invariant_digest))
        if isinstance(self.progress_ppm,bool) or not isinstance(self.progress_ppm,int) or not 0<=self.progress_ppm<=1_000_000: raise LongHorizonBenchmarkError("progress_ppm out of range")

@dataclass(frozen=True,slots=True)
class LongHorizonEpisode:
    episode_id:str; scenario_id:str; max_steps:int; checkpoints:tuple[HorizonCheckpoint,...]; completed:bool; autonomy_acceptance_digest:str
    def __post_init__(self):
        object.__setattr__(self,"episode_id",_token("episode_id",self.episode_id)); object.__setattr__(self,"scenario_id",_token("scenario_id",self.scenario_id)); object.__setattr__(self,"autonomy_acceptance_digest",_sha("autonomy_acceptance_digest",self.autonomy_acceptance_digest))
        if isinstance(self.max_steps,bool) or not isinstance(self.max_steps,int) or self.max_steps<=0: raise LongHorizonBenchmarkError("max_steps must be positive")
        if not self.checkpoints: raise LongHorizonBenchmarkError("checkpoints required")
        steps=[c.step for c in self.checkpoints]
        if steps!=sorted(steps) or len(steps)!=len(set(steps)): raise LongHorizonBenchmarkError("checkpoint steps must be strictly increasing")
        if any(step>self.max_steps for step in steps): raise LongHorizonBenchmarkError("checkpoint exceeds max_steps")
        progress=[c.progress_ppm for c in self.checkpoints]
        if progress!=sorted(progress): raise LongHorizonBenchmarkError("checkpoint progress cannot regress")
        if self.completed and progress[-1]!=1_000_000: raise LongHorizonBenchmarkError("completed episode requires full progress")
        if not isinstance(self.completed,bool): raise LongHorizonBenchmarkError("completed must be boolean")
    @property
    def digest(self)->str: return _digest({"episode_id":self.episode_id,"scenario_id":self.scenario_id,"max_steps":self.max_steps,"checkpoints":[{"step":c.step,"state":c.state_digest,"invariant":c.invariant_digest,"progress_ppm":c.progress_ppm} for c in self.checkpoints],"completed":self.completed,"autonomy_acceptance_digest":self.autonomy_acceptance_digest})
