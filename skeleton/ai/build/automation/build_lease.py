"""CAS lease preventing concurrent autonomous build writers."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class BuildLease:
 owner:str;epoch:int;head_sha:str
def acquire(current:BuildLease|None,*,owner:str,expected_epoch:int,head_sha:str)->BuildLease:
 if not owner or len(owner)>160:raise ValueError("invalid lease owner")
 if expected_epoch<0:raise ValueError("invalid lease epoch")
 if current is not None:
  if current.epoch!=expected_epoch:raise ValueError("stale build lease epoch")
  if current.owner!=owner:raise ValueError("build lease held by another owner")
  if current.head_sha!=head_sha:raise ValueError("build lease head changed")
 return BuildLease(owner,expected_epoch+1,head_sha)
