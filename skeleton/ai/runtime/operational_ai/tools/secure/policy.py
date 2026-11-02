"""Independent caller-signed tool authority, least-risk controls and expiry."""
from __future__ import annotations
from dataclasses import dataclass
import hmac,hashlib,time,json
from .spec import ToolInvocation,ToolSpec,ToolError

@dataclass(frozen=True,slots=True)
class ToolGrant:
    tenant:str
    user:str
    session:str
    tool_name:str
    spec_sha:str
    expires_ns:int
    nonce:str
    signature:str

@dataclass(frozen=True,slots=True)
class ToolDecision:
    admitted:bool
    reason:str
    risk:str


def _body(grant:ToolGrant)->bytes:
    return json.dumps([grant.tenant,grant.user,grant.session,grant.tool_name,
                       grant.spec_sha,grant.expires_ns,grant.nonce],separators=(',',':')).encode()

class ToolPolicy:
    def __init__(self,key:bytes,*,allow_risks:tuple[str,...]=('read',)):
        if not isinstance(key,bytes) or len(key)<32:
            raise ToolError('tool authority key requires 256 bits')
        if any(r not in {'read','write','external','privileged'} for r in allow_risks):
            raise ToolError('invalid risk allowlist')
        self._key=key
        self.allowed=frozenset(allow_risks)

    def mint(self,inv:ToolInvocation,*,expires_ns:int,nonce:str)->ToolGrant:
        if type(expires_ns) is not int or expires_ns<=time.time_ns() or expires_ns>time.time_ns()+86_400_000_000_000:
            raise ToolError('grant expiry invalid')
        if not isinstance(nonce,str) or not 16<=len(nonce)<=128 or not nonce.isascii():
            raise ToolError('grant nonce invalid')
        grant=ToolGrant(inv.tenant,inv.user,inv.session,inv.tool_name,inv.expected_spec_sha,expires_ns,nonce,'')
        signature=hmac.new(self._key,_body(grant),hashlib.sha256).hexdigest()
        return ToolGrant(*[getattr(grant,k) for k in ('tenant','user','session','tool_name','spec_sha','expires_ns','nonce')],signature)

    def check(self,spec:ToolSpec,inv:ToolInvocation,grant:ToolGrant,*,now_ns:int|None=None)->ToolDecision:
        now=time.time_ns() if now_ns is None else now_ns
        if spec.risk not in self.allowed:return ToolDecision(False,'risk-not-admitted',spec.risk)
        if type(grant.expires_ns) is not int or not now<=grant.expires_ns:return ToolDecision(False,'expired',spec.risk)
        fields=(inv.tenant,inv.user,inv.session,inv.tool_name,inv.expected_spec_sha)
        signed=(grant.tenant,grant.user,grant.session,grant.tool_name,grant.spec_sha)
        if fields!=signed:return ToolDecision(False,'scope-mismatch',spec.risk)
        expected=hmac.new(self._key,_body(grant),hashlib.sha256).hexdigest()
        if not isinstance(grant.signature,str) or not hmac.compare_digest(grant.signature,expected):
            return ToolDecision(False,'unauthenticated-grant',spec.risk)
        return ToolDecision(True,'explicit-grant',spec.risk)
