from dataclasses import dataclass
import hashlib,json,math
@dataclass(frozen=True)
class SystemSource: contract_id:str; contract_version:str; payload:dict
@dataclass(frozen=True)
class SystemCompilePlan: targets:tuple[str,...]
@dataclass(frozen=True)
class SystemArtifact:
 target:str; content:bytes; source_digest:str; derived:bool=True; grants_authority:bool=False
 def __post_init__(self):
  if self.derived is not True or self.grants_authority is not False:raise ValueError("compiled artifacts are derived and non-authoritative")
def _canonical(x):
 if isinstance(x,float) and not math.isfinite(x):raise ValueError("non-finite canonical value")
 if isinstance(x,dict):
  if any(not isinstance(k,str) for k in x):raise TypeError("canonical mapping keys must be strings")
  return {k:_canonical(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [_canonical(v) for v in x]
 return x
def compile_system(source,plan):
 if not source.contract_id or not source.contract_version or not plan.targets or any(not isinstance(t,str) or not t for t in plan.targets):raise ValueError("compiler source and targets required")
 raw=json.dumps(_canonical({"id":source.contract_id,"version":source.contract_version,"payload":source.payload}),sort_keys=True,separators=(",",":"),allow_nan=False).encode()
 digest=hashlib.sha256(raw).hexdigest()
 return tuple(SystemArtifact(t,(f"derived:{t}:{digest}\n").encode(),digest) for t in sorted(set(plan.targets)))
