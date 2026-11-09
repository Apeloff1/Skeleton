import pytest
from skeleton.security.contracts import SecretRef,SecurityContractError,SecurityIdentity
from skeleton.security.capability_security import AuthorizationReceipt,CapabilityGrant,SecurityContext,ToolRequest,authorize_tool_request
D="0"*64
def context():
 i=SecurityIdentity("worker-1","ctx-1")
 return SecurityContext(i,(CapabilityGrant("worker-1","repo.read","repo:a","read"),))
def test_exact_grant_authorizes_exact_request():
 r=authorize_tool_request(context(),ToolRequest("git","repo.read","repo:a","read",D))
 assert r.context_id=="ctx-1" and r.authority_scope=="tool-request-only"
@pytest.mark.parametrize("cap,res,op",[("repo.write","repo:a","read"),("repo.read","repo:b","read"),("repo.read","repo:a","write")])
def test_capability_resource_operation_mismatch_denied(cap,res,op):
 with pytest.raises(SecurityContractError):authorize_tool_request(context(),ToolRequest("git",cap,res,op,D))
def test_foreign_principal_grant_rejected():
 with pytest.raises(SecurityContractError):SecurityContext(SecurityIdentity("a","ctx"),(CapabilityGrant("b","x","y","z"),))
def test_duplicate_grants_fail_closed_as_ambiguous():
 g=CapabilityGrant("worker-1","repo.read","repo:a","read")
 with pytest.raises(SecurityContractError):authorize_tool_request(SecurityContext(SecurityIdentity("worker-1","ctx"),(g,g)),ToolRequest("git","repo.read","repo:a","read",D))
def test_receipt_cannot_escalate_scope():
 r=authorize_tool_request(context(),ToolRequest("git","repo.read","repo:a","read",D))
 with pytest.raises(SecurityContractError):AuthorizationReceipt(r.context_id,r.tool_id,r.request_digest,r.grant_digest,"session")
def test_secret_reference_contains_reference_not_value():
 r=SecretRef("vault","prod/api")
 assert not hasattr(r,"value")
def test_malformed_request_digest_rejected():
 with pytest.raises(SecurityContractError):ToolRequest("git","repo.read","repo:a","read","bad")
