from dataclasses import dataclass
@dataclass(frozen=True)
class ToolBinding: tool:str; permissions:frozenset[str]; input_schema:str; output_schema:str; trust:str
@dataclass(frozen=True)
class ToolComposition: bindings:tuple[ToolBinding,...]; granted:frozenset[str]
@dataclass(frozen=True)
class CompositionResult: valid:bool; reason:str
def validate(c):
 if any(not c.granted.issuperset(b.permissions) for b in c.bindings):return CompositionResult(False,"permission amplification")
 for a,b in zip(c.bindings,c.bindings[1:]):
  if a.output_schema!=b.input_schema:return CompositionResult(False,"schema mismatch")
  if a.trust!=b.trust:return CompositionResult(False,"trust boundary requires adapter")
 return CompositionResult(True,"valid")
