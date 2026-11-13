"""Human-origin authorization manifests. Plan/model text cannot mint grants."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import hmac
from ..core.canonical import canonical,identifier,hex_digest,uint,text
from ..core.errors import Unauthorized,Invalid
@dataclass(frozen=True,slots=True)
class Grant:
    plan:str
    step:str
    resource:str
    operation:str
    argument_sha256:str
    nonce:str
    expiry_ns:int
    signature:str
    def __post_init__(self):
        for k in ('plan','step','resource','operation','nonce'):identifier(getattr(self,k),k)
        hex_digest(self.argument_sha256,'args');hex_digest(self.signature,'signature')
        uint(self.expiry_ns,'expiry',1,2**63-1)
    def payload(self):return {k:getattr(self,k) for k in ('plan','step','resource','operation','argument_sha256','nonce','expiry_ns')}
    def record(self):return self.payload()|{'signature':self.signature}

def grant_from_operator(key:bytes,*,plan:str,step:str,resource:str,operation:str,argument_sha256:str,nonce:str,expiry_ns:int):
    if not isinstance(key,bytes) or len(key)<32:raise Unauthorized('operator signing key required')
    payload={'plan':identifier(plan),'step':identifier(step),'resource':identifier(resource),
             'operation':identifier(operation),'argument_sha256':hex_digest(argument_sha256),
             'nonce':identifier(nonce),'expiry_ns':uint(expiry_ns,'expiry',1,2**63-1)}
    signature=hmac.new(key,canonical(payload),sha256).hexdigest()
    return Grant(**payload,signature=signature)

def verify(key:bytes,grant:Grant,*,now_ns:int,plan:str,step:str,resource:str,operation:str,arguments:dict):
    if not isinstance(grant,Grant) or not isinstance(key,bytes) or len(key)<32:raise Unauthorized('trusted operator grant needed')
    if (grant.plan!=plan or grant.step!=step or grant.resource!=resource or grant.operation!=operation
        or grant.argument_sha256!=sha256(canonical(arguments)).hexdigest() or grant.expiry_ns<=now_ns):
        raise Unauthorized('grant does not bind current action')
    if not hmac.compare_digest(hmac.new(key,canonical(grant.payload()),sha256).hexdigest(),grant.signature):
        raise Unauthorized('grant signature invalid')
    return True
