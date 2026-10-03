"""Versioned durable envelope for autonomous build state."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass
from typing import Any,Mapping
SCHEMA="autonomous-studio.build-state-envelope.v1"
@dataclass(frozen=True)
class StateEnvelope:
 revision:int;head_sha:str;payload:Mapping[str,Any];sha256:str=""
 def sealed(self):
  if self.revision<0:raise ValueError("negative state revision")
  body={"schema":SCHEMA,"revision":self.revision,"head_sha":self.head_sha,"payload":self.payload}
  digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
  return StateEnvelope(self.revision,self.head_sha,self.payload,digest)
 def verify(self):
  if self.sha256!=self.sealed().sha256:raise ValueError("durable build state integrity mismatch")
def advance(previous:StateEnvelope|None,*,head_sha:str,payload:Mapping[str,Any])->StateEnvelope:
 revision=0 if previous is None else previous.revision+1
 if previous is not None:previous.verify()
 return StateEnvelope(revision,head_sha,dict(payload)).sealed()
