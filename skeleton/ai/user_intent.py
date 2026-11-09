"""Authoritative instruction lineage for VOL-329."""
from dataclasses import dataclass
@dataclass(frozen=True)
class IntentConstraint: key:str; value:str
@dataclass(frozen=True)
class UserIntent:
 intent_id:str; instruction:str; constraints:tuple[IntentConstraint,...]; authoritative:bool; inferred_summary:str|None=None
 def __post_init__(self):
  keys=[x.key for x in self.constraints]
  if not self.intent_id or not self.instruction or len(keys)!=len(set(keys)) or any(not x.key or not x.value for x in self.constraints) or not isinstance(self.authoritative,bool):raise ValueError("intent identity/instruction and unique constraints required")
@dataclass(frozen=True)
class IntentRevision:
 previous_id:str; current:UserIntent; reason:str
 def __post_init__(self):
  if self.current.intent_id==self.previous_id or not self.reason:raise ValueError("revision must supersede distinct intent with reason")
def reconcile_intent(current:UserIntent,new:UserIntent):
 if not current.authoritative:raise PermissionError("current intent lacks authoritative lineage")
 if not new.authoritative:raise PermissionError("inference cannot supersede authoritative instruction")
 old={x.key:x.value for x in current.constraints}; fresh={x.key:x.value for x in new.constraints}
 changed={k for k in old.keys()&fresh.keys() if old[k]!=fresh[k]}
 dropped=set(old)-set(fresh)
 return tuple(sorted(changed|dropped))
