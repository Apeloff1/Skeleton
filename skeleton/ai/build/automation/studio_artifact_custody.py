"""Content-addressed custody records for generated Studio artifacts."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
@dataclass(frozen=True)
class ArtifactCustody:
    kind:str; sha256:str; size:int
    @classmethod
    def from_bytes(cls,kind:str,data:bytes):
        if not kind or len(kind)>64: raise ValueError("invalid artifact kind")
        return cls(kind,hashlib.sha256(data).hexdigest(),len(data))
    def verify(self,data:bytes)->None:
        other=ArtifactCustody.from_bytes(self.kind,data)
        if other.sha256!=self.sha256 or other.size!=self.size: raise ValueError("artifact custody mismatch")
