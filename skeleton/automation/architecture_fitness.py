"""Executable architecture fitness registry for VOL-116."""
from dataclasses import dataclass
import re\n_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")\ndef _id(v,f):\n if not isinstance(v,str) or not _ID.fullmatch(v):raise FitnessError(f"{f} must be stable identifier")\n return v
class FitnessError(ValueError):pass
@dataclass(frozen=True)
class FitnessFunction:
 rule_id:str;decision_ref:str;pattern:str
 def __post_init__(self):
  object.__setattr__(self,"rule_id",_id(self.rule_id,"rule_id"));object.__setattr__(self,"decision_ref",_id(self.decision_ref,"decision_ref"))\n  if not isinstance(self.pattern,str) or not self.pattern:raise FitnessError("rule pattern required")
  try:re.compile(self.pattern)
  except re.error as e:raise FitnessError("invalid rule") from e
@dataclass(frozen=True)
class FitnessViolation:
 rule_id:str;path:str;line:int
@dataclass(frozen=True)
class FitnessWaiver:
 rule_id:str;path:str;owner_id:str;reason:str;expires_tick:int
 def __post_init__(self):
  if not self.owner_id or not self.reason or self.expires_tick<1:raise FitnessError("waiver must be narrow owned reasoned and expiring")
class FitnessRegistry:
 def __init__(self,rules):self.rules=tuple(rules)
 def evaluate(self,path,text):
  out=[]
  for rule in self.rules:
   rx=re.compile(rule.pattern)
   out.extend(FitnessViolation(rule.rule_id,path,n) for n,line in enumerate(text.splitlines(),1) if rx.search(line))
  return tuple(out)
 def unresolved(self,violations,waivers,tick):
  active={(w.rule_id,w.path) for w in waivers if w.expires_tick>=tick}
  return tuple(v for v in violations if (v.rule_id,v.path) not in active)
