"""Scope/time/version bounded approval reuse for VOL-327."""
from dataclasses import dataclass
@dataclass(frozen=True)
class ApprovalScope: subject:str; action:str; resource:str; version:str
@dataclass(frozen=True)
class ApprovalReusePolicy:
 max_uses:int; ttl:int
 def __post_init__(self):
  if isinstance(self.max_uses,bool) or isinstance(self.ttl,bool) or self.max_uses<=0 or self.ttl<=0:raise ValueError("positive approval reuse bounds required")
@dataclass(frozen=True)
class ApprovalBurden: requested:int; reused:int; stale:int; overridden:int
@dataclass(frozen=True)
class Approval:
 scope:ApprovalScope; approved_at:int; uses:int=0
 def reusable(self,scope,policy,now):
  return self.scope==scope and now>=self.approved_at and now-self.approved_at<policy.ttl and self.uses<policy.max_uses
 def reuse(self,scope,policy,now):
  if not self.reusable(scope,policy,now):raise PermissionError("approval scope/time/version boundary exceeded")
  return Approval(self.scope,self.approved_at,self.uses+1)
def burden(events):
 return ApprovalBurden(sum(e=="requested" for e in events),sum(e=="reused" for e in events),sum(e=="stale" for e in events),sum(e=="overridden" for e in events))
