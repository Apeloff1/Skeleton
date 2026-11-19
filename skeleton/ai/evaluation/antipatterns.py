"""Executable anti-pattern governance for VOL-108."""
from __future__ import annotations
from dataclasses import dataclass
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class AntiPatternError(ValueError):pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise AntiPatternError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class AntiPattern:
 pattern_id:str;failure_history:str;detector_regex:str;preferred_alternative:str
 def __post_init__(self):
  object.__setattr__(self,"pattern_id",_id(self.pattern_id,"pattern_id"))
  if not isinstance(self.failure_history,str) or not isinstance(self.preferred_alternative,str) or not self.failure_history.strip() or not self.preferred_alternative.strip():raise AntiPatternError("history and alternative required")
  if not isinstance(self.detector_regex,str) or not self.detector_regex:raise AntiPatternError("detector regex required")
  try:re.compile(self.detector_regex)
  except re.error as e:raise AntiPatternError("invalid detector regex") from e
@dataclass(frozen=True,slots=True)
class AntiPatternFinding:
 pattern_id:str;path:str;line:int;excerpt:str
 def __post_init__(self):
  object.__setattr__(self,"pattern_id",_id(self.pattern_id,"pattern_id"))
  if not isinstance(self.path,str) or not self.path.strip() or not isinstance(self.line,int) or isinstance(self.line,bool) or self.line<1:raise AntiPatternError("finding location invalid")
  if not isinstance(self.excerpt,str):raise AntiPatternError("finding excerpt invalid")
@dataclass(frozen=True,slots=True)
class AntiPatternException:
 pattern_id:str;path:str;owner_id:str;rationale:str;expires_tick:int
 def __post_init__(self):
  object.__setattr__(self,"pattern_id",_id(self.pattern_id,"pattern_id"));object.__setattr__(self,"owner_id",_id(self.owner_id,"owner_id"))
  if not isinstance(self.path,str) or not self.path.strip() or not isinstance(self.rationale,str) or not self.rationale.strip() or not isinstance(self.expires_tick,int) or isinstance(self.expires_tick,bool) or self.expires_tick<1:raise AntiPatternError("exception owner rationale and expiry required")
class AntiPatternRegistry:
 def __init__(self,patterns):self.patterns={p.pattern_id:p for p in patterns}
 def scan(self,path,text):
  out=[]
  for p in self.patterns.values():
   rx=re.compile(p.detector_regex)
   for n,line in enumerate(text.splitlines(),1):
    if rx.search(line):out.append(AntiPatternFinding(p.pattern_id,path,n,line.strip()))
  return tuple(sorted(out,key=lambda x:(x.path,x.line,x.pattern_id)))
 def unresolved(self,findings,exceptions,current_tick):
  active={(e.pattern_id,e.path) for e in exceptions if e.expires_tick>=current_tick}
  return tuple(f for f in findings if (f.pattern_id,f.path) not in active)
