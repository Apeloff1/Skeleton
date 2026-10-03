"""Detect autonomous build deadlocks from lack of state movement."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class Deadlock:
 detected:bool;reason:str
def detect(*,fingerprints:tuple[str,...],pending_repairs:int,queued_tasks:int)->Deadlock:
 if len(fingerprints)>=4 and len(set(fingerprints[-4:]))==1 and (pending_repairs or queued_tasks):
  return Deadlock(True,"four cycles without canonical state movement")
 return Deadlock(False,"state progressing")
