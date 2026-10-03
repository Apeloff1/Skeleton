"""Monotonic progress accounting across autonomous build cycles."""
from dataclasses import dataclass
@dataclass(frozen=True)
class BuildProgress:
 total:int; done:int; rejected:int; blocked:int; queued:int
 def __post_init__(self):
  if any(v<0 for v in (self.total,self.done,self.rejected,self.blocked,self.queued)): raise ValueError("negative progress")
  if self.done+self.rejected+self.blocked+self.queued>self.total: raise ValueError("progress exceeds total")
 @property
 def terminal(self): return self.queued==0 and self.blocked==0
 @property
 def completed_fraction(self): return 1.0 if self.total==0 else (self.done+self.rejected)/self.total
