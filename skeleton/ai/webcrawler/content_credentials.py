"""Content credential observations supplied by an external verifier.

The crawler never treats missing credentials as proof of authenticity.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
@dataclass(frozen=True)
class CredentialObservation:
 status:str
 issuer:str|None=None
 manifest_digest:str|None=None
 details:Mapping[str,object]|None=None
 def __post_init__(self):
  if self.status not in {"verified","invalid","absent","unknown"}:raise ValueError("unsupported credential status")
def credential_trust_delta(observation:CredentialObservation)->float:
 if observation.status=="verified":return .05
 if observation.status=="invalid":return -.25
 return 0.0
