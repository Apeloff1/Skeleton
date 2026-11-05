"""Independent authority to grant effects; model output is never an approval."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import hmac,time
from .contracts import Identity,Conflict,SpineError,identifier,canonical,hexdigest

@dataclass(frozen=True,slots=True)
class EffectGrant:
    tenant:str
    subject:str
    model_sha256:str
    operation:str
    args_sha256:str
    expires_at_ns:int
    grant_id:str
    def __post_init__(self):
        for name in ('tenant','subject','operation','grant_id'):identifier(getattr(self,name),name)
        hexdigest(self.model_sha256);hexdigest(self.args_sha256)
        if type(self.expires_at_ns)is not int or self.expires_at_ns<=0:raise SpineError('invalid expiry')
    def record(self):return {k:getattr(self,k) for k in self.__dataclass_fields__}

def require_effect(identity:Identity,grant:EffectGrant,operation:str,args:dict,*,
                   authorizing_key:bytes,signature:str):
    if not isinstance(identity,Identity) or not isinstance(grant,EffectGrant):raise Conflict('independent effect grant required')
    identifier(operation,'operation')
    if len(authorizing_key)<32:raise Conflict('independent authorization key unavailable')
    hexdigest(signature,'grant signature')
    expected=hmac.new(authorizing_key,canonical(grant.record()),'sha256').hexdigest()
    if not hmac.compare_digest(expected,signature):raise Conflict('tool grant signature invalid')
    if grant.tenant!=identity.tenant or grant.subject!=identity.subject or grant.model_sha256!=identity.model_sha256:
        raise Conflict('tool grant belongs to different owner or model')
    if operation!=grant.operation or sha256(canonical(args)).hexdigest()!=grant.args_sha256:
        raise Conflict('effect or argument digest outside approval')
    if time.time_ns()>=grant.expires_at_ns:raise Conflict('effect grant expired')
    return True
