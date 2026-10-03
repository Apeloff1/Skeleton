"""Lifecycle for CI-derived repair work."""
from __future__ import annotations
from dataclasses import dataclass
TRANSITIONS={"observed":{"admitted","quarantined"},"admitted":{"building","quarantined"},"building":{"validating","failed"},"validating":{"accepted","failed"},"failed":{"admitted","quarantined"},"accepted":{"retired"},"quarantined":set(),"retired":set()}
@dataclass(frozen=True)
class RepairLifecycle:
 id:str;state:str="observed";attempt:int=0
 def transition(self,target:str):
  if target not in TRANSITIONS.get(self.state,set()):raise ValueError(f"illegal repair transition {self.state}->{target}")
  attempt=self.attempt+(1 if target=="building" else 0)
  if attempt>3:raise ValueError("repair attempt budget exhausted")
  return RepairLifecycle(self.id,target,attempt)
