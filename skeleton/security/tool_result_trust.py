from dataclasses import dataclass
@dataclass(frozen=True)
class ToolEvidence: source:str; observed_at:int; independent:bool
@dataclass(frozen=True)
class ToolResultTrust: level:str; provenance:tuple[ToolEvidence,...]; instruction_authority:bool=False
@dataclass(frozen=True)
class ToolValidation: valid:bool; reason:str
def validate_result(t,high_impact=False):
 if t.instruction_authority:return ToolValidation(False,"tool output cannot be instruction authority")
 if high_impact and not any(e.independent for e in t.provenance):return ToolValidation(False,"independent validation required")
 return ToolValidation(bool(t.provenance),"provenance checked")
