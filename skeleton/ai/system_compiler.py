from dataclasses import dataclass
import hashlib,json
@dataclass(frozen=True)
class SystemSource: contract_id:str; contract_version:str; payload:dict
@dataclass(frozen=True)
class SystemCompilePlan: targets:tuple[str,...]
@dataclass(frozen=True)
class SystemArtifact: target:str; content:bytes; source_digest:str; derived:bool=True; grants_authority:bool=False
def compile_system(source,plan):
 raw=json.dumps({"id":source.contract_id,"version":source.contract_version,"payload":source.payload},sort_keys=True,separators=(",",":")).encode();digest=hashlib.sha256(raw).hexdigest()
 return tuple(SystemArtifact(t,(f"derived:{t}:{digest}\n").encode(),digest) for t in sorted(set(plan.targets)))
