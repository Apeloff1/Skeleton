"""Workload-identity zero-trust authorization for VOL-170."""
from __future__ import annotations
from dataclasses import dataclass
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class TrustError(ValueError):pass
@dataclass(frozen=True,slots=True)
class WorkloadIdentity:
 workload_id:str;instance_id:str;attestation_digest:str
 def __post_init__(self):
  if not _ID.fullmatch(self.workload_id) or not _ID.fullmatch(self.instance_id) or not _SHA.fullmatch(self.attestation_digest):raise TrustError("invalid workload identity")
@dataclass(frozen=True,slots=True)
class InternalGrant:
 grant_id:str;workload_id:str;instance_id:str;actions:frozenset[str];resource_prefix:str;issued_tick:int;expires_tick:int
 def __post_init__(self):
  if not _ID.fullmatch(self.grant_id) or not self.actions or not self.resource_prefix or self.issued_tick<0 or self.expires_tick<=self.issued_tick:raise TrustError("invalid grant")
@dataclass(frozen=True,slots=True)
class TrustDecision:
 allowed:bool;reason:str;grant_id:str|None;revalidate_at:int|None
def authorize(identity,grant,action,resource,now,revalidation_interval=10):
 if grant.workload_id!=identity.workload_id or grant.instance_id!=identity.instance_id:return TrustDecision(False,"identity_mismatch",None,None)
 if now<grant.issued_tick or now>=grant.expires_tick:return TrustDecision(False,"grant_expired",None,None)
 if action not in grant.actions or not resource.startswith(grant.resource_prefix):return TrustDecision(False,"least_privilege_denied",None,None)
 if revalidation_interval<1:raise TrustError("revalidation interval must be positive")
 return TrustDecision(True,"authorized",grant.grant_id,min(grant.expires_tick,now+revalidation_interval))
def revalidate(identity,grant,decision,now):
 if not decision.allowed or decision.grant_id!=grant.grant_id:raise TrustError("invalid prior decision")
 return authorize(identity,grant,next(iter(grant.actions)),grant.resource_prefix,now)
