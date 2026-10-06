"""Exact-match runtime authorization over capability contracts."""
from dataclasses import dataclass
from hashlib import sha256
import json,re
from .capability_contracts import CapabilityGrant,SecurityContractError
_SHA=re.compile(r"^[0-9a-f]{64}$")
@dataclass(frozen=True,slots=True)
class SecurityContext:
 principal_id:str
 context_id:str
 grants:tuple[CapabilityGrant,...]
 def __post_init__(self):
  if not self.principal_id or not self.context_id:raise SecurityContractError("identity required")
  if not isinstance(self.grants,tuple):raise SecurityContractError("grants must be tuple")
  if any(not isinstance(g,CapabilityGrant) or g.principal_id!=self.principal_id for g in self.grants):raise SecurityContractError("foreign grant")
@dataclass(frozen=True,slots=True)
class ToolRequest:
 tool_id:str
 capability:str
 resource:str
 operation:str
 request_digest:str
 def __post_init__(self):
  if not all(isinstance(x,str) and x and x==x.strip() for x in (self.tool_id,self.capability,self.resource,self.operation)):raise SecurityContractError("request fields required")
  if not isinstance(self.request_digest,str) or not _SHA.fullmatch(self.request_digest):raise SecurityContractError("invalid request digest")
@dataclass(frozen=True,slots=True)
class AuthorizationReceipt:
 context_id:str
 tool_id:str
 request_digest:str
 grant_digest:str
 scope:str="single-tool-request"
 def __post_init__(self):
  if self.scope!="single-tool-request":raise SecurityContractError("invalid authorization scope")
def _grant_digest(g):
 return sha256(json.dumps({"principal_id":g.principal_id,"capability":g.capability,"resource":g.resource,"operation":g.operation},sort_keys=True,separators=(",",":")).encode()).hexdigest()
def authorize_tool_request(context:SecurityContext,request:ToolRequest)->AuthorizationReceipt:
 if not isinstance(context,SecurityContext) or not isinstance(request,ToolRequest):raise SecurityContractError("typed inputs required")
 matches=[g for g in context.grants if (g.capability,g.resource,g.operation)==(request.capability,request.resource,request.operation)]
 if len(matches)!=1:raise SecurityContractError("request not authorized")
 return AuthorizationReceipt(context.context_id,request.tool_id,request.request_digest,_grant_digest(matches[0]))
