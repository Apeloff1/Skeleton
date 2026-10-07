"""Delivery decision for a completed autonomous build."""
from dataclasses import dataclass
@dataclass(frozen=True)
class DeliveryState:
 campaign_complete:bool; build_complete:bool; required_ci_green:bool; patch_present:bool; certificate_present:bool
 @property
 def deliverable(self): return all((self.campaign_complete,self.build_complete,self.required_ci_green,self.patch_present,self.certificate_present))
 def require(self):
  if not self.deliverable: raise ValueError("build delivery requirements are incomplete")
