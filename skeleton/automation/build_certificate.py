"""Final certificate for an autonomously completed build campaign."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass,asdict
from typing import Sequence
@dataclass(frozen=True)
class BuildCertificate:
 build_id:str; base_sha:str; final_sha:str; cycles:int; accepted:int; outcome_sha256:tuple[str,...]; status:str
 def validate(self):
  if self.status!="complete": raise ValueError("cannot certify incomplete build")
  if self.cycles<1 or self.accepted<0: raise ValueError("invalid build counters")
  for name,value in (("base",self.base_sha),("final",self.final_sha)):
   if len(value)!=40 or any(c not in "0123456789abcdef" for c in value): raise ValueError(f"invalid {name} sha")
  for value in self.outcome_sha256:
   if len(value)!=64 or any(c not in "0123456789abcdef" for c in value): raise ValueError("invalid outcome digest")
 def digest(self):
  self.validate(); return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(",",":")).encode()).hexdigest()
