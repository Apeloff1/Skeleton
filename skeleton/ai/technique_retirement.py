from dataclasses import dataclass
@dataclass(frozen=True)
class Technique: technique_id:str; version:str; consumers:tuple[str,...]
@dataclass(frozen=True)
class RetirementEvidence: reason:str; replacement:str; archive:str; migrated_consumers:frozenset[str]
@dataclass(frozen=True)
class TechniqueRetirement: technique:Technique; evidence:RetirementEvidence; retired:bool
def retire(t,e):
 if not t.technique_id or not t.version or len(t.consumers)!=len(set(t.consumers)) or any(not c for c in t.consumers):raise ValueError("valid technique inventory required")
 if e.replacement==t.technique_id:raise ValueError("replacement must differ from retired technique")
 if not all((e.reason,e.replacement,e.archive)):raise ValueError("retirement evidence incomplete")
 if not set(t.consumers).issubset(e.migrated_consumers):raise PermissionError("technique still on critical consumer path")
 return TechniqueRetirement(t,e,True)
