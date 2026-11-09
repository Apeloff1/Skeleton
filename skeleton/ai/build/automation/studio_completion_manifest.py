"""Final machine-verifiable manifest for a Studio completion run."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class CompletionManifest:
    run_id:str; base_sha:str; generation_id:str; accepted_tasks:tuple[str,...]; patch_sha256:str; outcome_sha256:tuple[str,...]
    def digest(self)->str:
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(",",":")).encode()).hexdigest()
    def validate(self)->None:
        if not self.run_id or not self.generation_id: raise ValueError("manifest identity missing")
        for value in (self.base_sha,self.patch_sha256,*self.outcome_sha256):
            if len(value)!=64 and len(value)!=40: raise ValueError("manifest digest malformed")
