"""Classify deterministic build blockers into bounded next actions."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class Blocker:
 kind:str; retryable:bool; action:str
def classify(*,validation_failed=False,ci_failed=False,dependency_blocked=False,authority_invalid=False)->Blocker:
 if authority_invalid:return Blocker("authority",False,"quarantine")
 if dependency_blocked:return Blocker("dependency",False,"replan")
 if validation_failed:return Blocker("validation",True,"repair")
 if ci_failed:return Blocker("integration_ci",True,"diagnose")
 return Blocker("none",False,"continue")
