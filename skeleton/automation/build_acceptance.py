"""Independent acceptance matrix for autonomous build completion."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class Acceptance:
 canonical_drained:bool; integration_green:bool; required_ci_green:bool; receipts_verified:bool; crash_journal_clear:bool
 @property
 def complete(self):return all((self.canonical_drained,self.integration_green,self.required_ci_green,self.receipts_verified,self.crash_journal_clear))
 def require_complete(self):
  if not self.complete:raise ValueError("autonomous build acceptance incomplete")
