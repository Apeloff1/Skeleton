"""Prerequisite-bound anti-starvation curriculum engine for VOL-151."""
from __future__ import annotations
from dataclasses import dataclass
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class CurriculumError(ValueError): pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v): raise CurriculumError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class CurriculumStage:
 stage_id:str;competency_id:str;prerequisites:tuple[str,...];required:bool;pass_threshold:float
 def __post_init__(self):
  object.__setattr__(self,"stage_id",_id(self.stage_id,"stage_id"));object.__setattr__(self,"competency_id",_id(self.competency_id,"competency_id"))
  if not 0<=self.pass_threshold<=1: raise CurriculumError("threshold outside [0,1]")
@dataclass(frozen=True,slots=True)
class ProgressSignal:
 stage_id:str;score:float;attempt:int
 def __post_init__(self):
  object.__setattr__(self,"stage_id",_id(self.stage_id,"stage_id"))
  if not 0<=self.score<=1 or self.attempt<1: raise CurriculumError("invalid progress signal")
class Curriculum:
 def __init__(self,stages):
  stages=tuple(stages);self.stages={s.stage_id:s for s in stages}
  if len(stages)!=len(self.stages): raise CurriculumError("duplicate stage")
  for s in stages:
   if s.stage_id in s.prerequisites or any(p not in self.stages for p in s.prerequisites): raise CurriculumError("invalid prerequisite")
  self._check_cycles()
 def _check_cycles(self):
  visiting=set();done=set()
  def visit(n):
   if n in visiting: raise CurriculumError("curriculum cycle")
   if n in done:return
   visiting.add(n)
   for p in self.stages[n].prerequisites:visit(p)
   visiting.remove(n);done.add(n)
  for n in self.stages:visit(n)
 def completed(self,signals):
  best={}
  for x in signals:best[x.stage_id]=max(best.get(x.stage_id,0),x.score)
  return {sid for sid,s in self.stages.items() if best.get(sid,0)>=s.pass_threshold}
 def ready(self,signals):
  complete=self.completed(signals)
  return tuple(sorted(s.stage_id for s in self.stages.values() if s.stage_id not in complete and set(s.prerequisites)<=complete))
 def curriculum_complete(self,signals):
  complete=self.completed(signals);return all(not s.required or s.stage_id in complete for s in self.stages.values())