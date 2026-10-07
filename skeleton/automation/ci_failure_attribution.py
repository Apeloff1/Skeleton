"""Deterministic attribution of CI failures to bounded repair classes."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class Attribution:
 gate:str; category:str; action:str; retryable:bool
def attribute(gate:str)->Attribution:
 n=gate.lower()
 if "workflow input" in n or "secret" in n or "malware" in n:return Attribution(gate,"trust","quarantine",False)
 if "backend quality" in n or "ci/cd" in n:return Attribution(gate,"code_quality","repair",True)
 if "studio" in n:return Attribution(gate,"studio_regression","repair",True)
 if "arm64" in n:return Attribution(gate,"portability","repair",True)
 if "merge readiness" in n:return Attribution(gate,"integration","diagnose",True)
 if "hygiene" in n:return Attribution(gate,"repository_hygiene","repair",True)
 return Attribution(gate,"unknown","diagnose",False)
