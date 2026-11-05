"""Tool proposals are inert plans requiring external operator approval.

No model-produced tool intent can execute a shell command, touch network,
read arbitrary filesystem paths or become a signed grant by itself.
"""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import Scope,identifier,sha,integer,exact,refuse,fingerprint
@dataclass(frozen=True,slots=True)
class ToolIntent:
    request_id:str
    tool:str
    scope_sha256:str
    args_sha256:str
    expires_ns:int
    intent_id:str
    def __post_init__(self):
        identifier(self.request_id);identifier(self.tool);identifier(self.intent_id)
        sha(self.scope_sha256);sha(self.args_sha256)
        integer(self.expires_ns,minimum=1)
def propose(scope,*,request_id,tool,arguments,expires_ns):
    if type(scope) is not Scope:refuse("tool proposal requires model-bound identity")
    if tool not in ("read_source","list_sources","search_local","inspect_receipt"):
        refuse("tool not in read-only offline capability set")
    exact(arguments,("source_id","limit"))
    identifier(arguments["source_id"]);integer(arguments["limit"],minimum=1,maximum=100)
    integer(expires_ns,minimum=1)
    receipt=fingerprint({"scope":scope.receipt(),"request_id":request_id,
                         "tool":tool,"arguments":arguments,
                         "expires_ns":expires_ns})
    return ToolIntent(identifier(request_id),tool,scope.digest(),
                      fingerprint(arguments),expires_ns,"intent_"+receipt[:24])
def inspect(intent,scope,*,now_ns,tool,operator_grant_sha256=None):
    if type(intent) is not ToolIntent or type(scope) is not Scope:
        refuse("untrusted tool intent")
    integer(now_ns)
    if intent.scope_sha256!=scope.digest() or intent.tool!=tool:
        refuse("cross-principal or wrong tool intent")
    if now_ns>=intent.expires_ns:refuse("expired tool intent")
    if operator_grant_sha256 is None:
        return {"intent_id":intent.intent_id,"state":"proposed",
                "executable":False,"operator_grant_missing":True}
    sha(operator_grant_sha256)
    return {"intent_id":intent.intent_id,"state":"grant-input-received",
            "executable":False,"external_grant_not_verified_here":True}
