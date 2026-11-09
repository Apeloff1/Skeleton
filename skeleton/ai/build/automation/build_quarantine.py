"""Structured quarantine record for work automation must not continue."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class Quarantine:
 kind:str;identity:str;head_sha:str;reason:str;evidence_sha256:str
 def digest(self):
  if len(self.evidence_sha256)!=64:raise ValueError("quarantine evidence malformed")
  return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(",",":")).encode()).hexdigest()
