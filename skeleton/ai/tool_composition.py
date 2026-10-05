from dataclasses import dataclass
@dataclass(frozen=True)
class ToolBinding: tool:str; permissions:frozenset[str]; input_schema:str; output_schema:str; trust:str
@dataclass(frozen=True)
class ToolComposition: bindings:tuple[ToolBinding,...]; granted:frozenset[str]
@dataclass(frozen=True)
class CompositionResult: valid:bool; reason:str
def validate(c):
 if not c.bindings:return CompositionResult(False,"empty composition")
 if any(not p for p in c.granted):return CompositionResult(False,"invalid granted permission")
 names=[b.tool for b in c.bindings]
 if len(names)!=len(set(names)):return CompositionResult(False,"duplicate tool binding")
 if any(not b.tool or not b.input_schema or not b.output_schema or not b.trust or any(not p for p in b.permissions) for b in c.bindings):return CompositionResult(False,"invalid binding")
 if any(not b.permissions.issubset(c.granted) for b in c.bindings):return CompositionResult(False,"permission amplification")
 effective=set(c.bindings[0].permissions)
 for b in c.bindings[1:]:effective.intersection_update(b.permissions)
 used=set().union(*(b.permissions for b in c.bindings))
 if used-effective:return CompositionResult(False,"composition would aggregate authority")
 for a,b in zip(c.bindings,c.bindings[1:]):
  if a.output_schema!=b.input_schema:return CompositionResult(False,"schema mismatch")
  if a.trust!=b.trust:return CompositionResult(False,"trust boundary requires adapter")
 return CompositionResult(True,"valid")
