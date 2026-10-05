"""Authoritative instruction lineage for VOL-329."""
from dataclasses import dataclass
@dataclass(frozen=True)
class IntentConstraint: key:str; value:str
@dataclass(frozen=True)
class UserIntent:
 intent_id:str; instruction:str; constraints:tuple[IntentConstraint,...]; authoritative:bool; inferred_summary:str|None=None
@dataclass(frozen=True)
class IntentRevision:
 previous_id:str; current:UserIntent; reason:str
 def __post_init__(self):
  if self.current.intent_id==self.previous_id or not self.reason:raise ValueError("revision must supersede distinct intent with reason")
def reconcile_intent(current:UserIntent,new:UserIntent):
 if not new.authoritative:raise PermissionError("inference cannot supersede authoritative instruction")
 old={x.key:x.value for x in current.constraints}; fresh={x.key:x.value for x in new.constraints}
 conflicts=tuple(sorted(k for k in old.keys()&fresh.keys() if old[k]!=fresh[k]))
 return conflicts
