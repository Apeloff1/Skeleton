"""Exact principal/deadline/evidence admission for real offline operations."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import Scope,identifier,sha,integer,number,refuse,fingerprint
@dataclass(frozen=True,slots=True)
class Permit:
    scope:Scope
    source_sha256:str
    operation:str
    revision:int
    issued_ns:int
    expires_ns:int
    verified:bool
    def __post_init__(self):
        if type(self.scope) is not Scope:refuse("principal scope required")
        sha(self.source_sha256)
        identifier(self.operation)
        integer(self.revision,minimum=1,maximum=1000000000)
        integer(self.issued_ns)
        integer(self.expires_ns,minimum=self.issued_ns+1)
        if self.expires_ns-self.issued_ns>60_000_000_000:
            refuse("source permit cannot outlive 60 seconds")
        if type(self.verified) is not bool:refuse("verified flag cannot coerce")
    def claims(self):
        return {"scope":self.scope.receipt(),"source_sha256":self.source_sha256,
                "operation":self.operation,"revision":self.revision,
                "issued_ns":self.issued_ns,"expires_ns":self.expires_ns}
    def evidence_sha256(self):
        return fingerprint(self.claims())
def admit(permit,scope,operation,*,now_ns,required_source_sha256):
    if type(permit) is not Permit or type(scope) is not Scope:
        refuse("typed operator permit and scope required")
    permit.scope.assert_same(scope)
    identifier(operation);integer(now_ns);sha(required_source_sha256)
    if permit.operation!=operation:refuse("tool or operation privilege mismatch")
    if permit.source_sha256!=required_source_sha256:
        refuse("approved source revision differs")
    if not permit.verified:refuse("externally unverified source claim")
    if not permit.issued_ns<=now_ns<permit.expires_ns:
        refuse("source permission expired or not active")
    return {"permitted":True,"scope_sha256":scope.digest(),
            "permit_sha256":permit.evidence_sha256(),
            "external_source_authenticated_by_this_function":False}
