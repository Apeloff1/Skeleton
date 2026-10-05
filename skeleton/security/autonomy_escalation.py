"""Approval-bound, expiring autonomy escalation for VOL-319."""
from dataclasses import dataclass
@dataclass(frozen=True)
class EscalationEvidence: evidence_id:str; eligible:bool; approver_id:str|None
@dataclass(frozen=True)
class AutonomyEscalation: request_id:str; subject_id:str; requested_level:int; evidence:EscalationEvidence
@dataclass(frozen=True)
class EscalationGrant:
 request_id:str; subject_id:str; level:int; issued_at:int; expires_at:int; revoked_at:int|None=None
 def __post_init__(self):
  if self.expires_at<=self.issued_at:raise ValueError("grant must expire")
 def active(self,now:int):return self.revoked_at is None and self.issued_at<=now<self.expires_at
 def revoke(self,now:int):
  if now<self.issued_at:raise ValueError("invalid revocation time")
  return EscalationGrant(self.request_id,self.subject_id,self.level,self.issued_at,self.expires_at,now)
def approve_escalation(request:AutonomyEscalation,*,now:int,ttl:int,max_level:int):
 if not request.evidence.eligible or not request.evidence.approver_id:raise PermissionError("independent eligibility and approval required")
 if request.requested_level>max_level or ttl<=0:raise PermissionError("escalation outside policy")
 return EscalationGrant(request.request_id,request.subject_id,request.requested_level,now,now+ttl)
