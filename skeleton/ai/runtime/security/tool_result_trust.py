from dataclasses import dataclass
_LEVELS=frozenset({"untrusted","context","verified"})
@dataclass(frozen=True)
class ToolEvidence: source:str; observed_at:int; independent:bool
@dataclass(frozen=True)
class ToolResultTrust:
 level:str; provenance:tuple[ToolEvidence,...]; instruction_authority:bool=False
 def __post_init__(self):
  if self.level not in _LEVELS or not isinstance(self.instruction_authority,bool):raise ValueError("invalid tool trust level")
@dataclass(frozen=True)
class ToolValidation: valid:bool; reason:str
def validate_result(t,high_impact=False,now=None,max_age=None):
 if t.instruction_authority:return ToolValidation(False,"tool output cannot be instruction authority")
 if any(not e.source or not isinstance(e.independent,bool) for e in t.provenance):return ToolValidation(False,"invalid provenance")
 if now is not None and max_age is not None and any(e.observed_at>now or now-e.observed_at>max_age for e in t.provenance):return ToolValidation(False,"stale provenance")
 if high_impact and not any(e.independent for e in t.provenance):return ToolValidation(False,"independent validation required")
 if t.level=="verified" and not any(e.independent for e in t.provenance):return ToolValidation(False,"verified trust requires independent provenance")
 return ToolValidation(bool(t.provenance),"provenance checked")
