from dataclasses import dataclass
@dataclass(frozen=True)
class ScopeDimension: name:str; value:str
@dataclass(frozen=True)
class ClaimScope:
 dimensions:tuple[ScopeDimension,...]
 def __post_init__(self):
  names=[d.name for d in self.dimensions]
  if not self.dimensions or any(not isinstance(d.name,str) or not isinstance(d.value,str) or not d.name.strip() or not d.value.strip() for d in self.dimensions) or len(names)!=len(set(names)):raise ValueError("scope dimensions must be unique and nonempty")
@dataclass(frozen=True)
class ScopeCompatibility: compatible:bool; conflicts:tuple[str,...]
def compare_scope(a,b):
 x={d.name:d.value for d in a.dimensions};y={d.name:d.value for d in b.dimensions}
 conflicts=tuple(sorted(k for k in x.keys()|y.keys() if k not in x or k not in y or x[k]!=y[k]))
 return ScopeCompatibility(not conflicts,conflicts)
def require_compatible(a,b):
 r=compare_scope(a,b)
 if not r.compatible:raise ValueError("claim scopes require explicit qualification")
 return r
