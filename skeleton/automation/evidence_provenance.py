"""Hash-linked provenance chain for autonomous build evidence."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class EvidenceNode:
 kind:str;identity:str;payload_sha256:str;previous_sha256:str=""
 def validate(self):
  for x in (self.payload_sha256,)+( (self.previous_sha256,) if self.previous_sha256 else ()):
   if len(x)!=64 or any(c not in "0123456789abcdef" for c in x):raise ValueError("malformed evidence digest")
 def digest(self):
  self.validate();return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(",",":")).encode()).hexdigest()
def append(kind:str,identity:str,payload_sha256:str,previous:EvidenceNode|None=None)->EvidenceNode:
 n=EvidenceNode(kind,identity,payload_sha256,previous.digest() if previous else "");n.validate();return n
