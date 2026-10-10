"""Least-privilege capability authorization for runtime tool requests."""
from dataclasses import dataclass
from hashlib import sha256
import json,re
from .contracts import SecurityContractError,SecurityIdentity
_SHA=re.compile(r"^[0-9a-f]{64}$")
@dataclass(frozen=True,slots=True)
class CapabilityGrant:
 principal_id:str
 capability:str
 resource:str
 operation:str
 @property
 def digest(self):
  return sha256(json.dumps({"principal_id":self.principal_id,"capability":self.capability,"resource":self.resource,"operation":self.operation},sort_keys=True,separators=(",",":")).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class SecurityContext:
 identity:SecurityIdentity
 grants:tuple[CapabilityGrant,...]
 def __post_init__(self):
  if not isinstance(self.identity,SecurityIdentity) or not isinstance(self.grants,tuple):raise SecurityContractError("invalid security context")
  for grant in self.grants:
   if not isinstance(grant,CapabilityGrant) or grant.principal_id!=self.identity.principal_id:raise SecurityContractError("foreign capability grant")
  object.__setattr__(self,"grants",tuple(sorted(self.grants,key=lambda x:x.digest)))
 def authorize(self,capability:str,resource:str,operation:str)->CapabilityGrant:
  matches=[g for g in self.grants if (g.capability,g.resource,g.operation)==(capability,resource,operation)]
  if len(matches)!=1:raise SecurityContractError("capability denied")
  return matches[0]
@dataclass(frozen=True,slots=True)
class ToolRequest:
 tool_id:str
 capability:str
 resource:str
 operation:str
 request_digest:str
 def __post_init__(self):
  if not isinstance(self.request_digest,str) or not _SHA.fullmatch(self.request_digest):raise SecurityContractError("invalid request digest")
@dataclass(frozen=True,slots=True)
class AuthorizationReceipt:
 context_id:str
 tool_id:str
 request_digest:str
 grant_digest:str
 authority_scope:str="tool-request-only"
 def __post_init__(self):
  if self.authority_scope!="tool-request-only":raise SecurityContractError("authorization scope escalation")
def authorize_tool_request(context:SecurityContext,request:ToolRequest)->AuthorizationReceipt:
 if not isinstance(context,SecurityContext) or not isinstance(request,ToolRequest):raise SecurityContractError("typed authorization inputs required")
 grant=context.authorize(request.capability,request.resource,request.operation)
 return AuthorizationReceipt(context.identity.context_id,request.tool_id,request.request_digest,grant.digest)
