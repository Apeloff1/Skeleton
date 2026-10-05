from dataclasses import dataclass
@dataclass(frozen=True)
class ScopeDimension: name:str; value:str
@dataclass(frozen=True)
class ClaimScope: dimensions:tuple[ScopeDimension,...]
@dataclass(frozen=True)
class ScopeCompatibility: compatible:bool; conflicts:tuple[str,...]
def compare_scope(a,b):
 x={d.name:d.value for d in a.dimensions};y={d.name:d.value for d in b.dimensions};c=tuple(sorted(k for k in x.keys()&y.keys() if x[k]!=y[k]))
 return ScopeCompatibility(not c,c)
def require_compatible(a,b):
 r=compare_scope(a,b)
 if not r.compatible:raise ValueError("claim scopes require explicit qualification")
 return r
