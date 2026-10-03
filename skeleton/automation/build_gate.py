"""Publication gate for autonomous build continuation and delivery."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class BuildGate:
 patch_present:bool; validation_passed:bool; exact_head_ci_required:bool=True; operator_hold:bool=False
 @property
 def publishable(self): return self.patch_present and self.validation_passed and not self.operator_hold
 @property
 def continuable(self): return self.validation_passed and not self.operator_hold
 def require_publishable(self):
  if not self.publishable: raise ValueError("autonomous build is not publishable")
