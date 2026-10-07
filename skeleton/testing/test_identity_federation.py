from __future__ import annotations
import hashlib,pytest
from skeleton.ai.runtime.security.identity_federation import FederatedPrincipalMapping,FederatedSessionEvidence,IdentityFederationError,authorize_federated_session
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def mapping():
    return FederatedPrincipalMapping("issuer","subject","principal","tenant",("read","write"),d("map"))
def session(epoch=1):
    return FederatedSessionEvidence("s","principal","tenant","issuer",("read","write"),100,1000,epoch)
def test_federated_session_maps_scopes_and_revocation():
    result=authorize_federated_session(mapping=mapping(),session=session(),requested_scopes=("read",),now_ns=500,current_revocation_epoch=1)
    assert result.allowed is True and result.effective_scopes==("read",)
def test_revoked_session_fails_closed():
    result=authorize_federated_session(mapping=mapping(),session=session(1),requested_scopes=("read",),now_ns=500,current_revocation_epoch=2)
    assert result.allowed is False and "session-revoked" in result.reasons
def test_scope_escalation_is_denied():
    result=authorize_federated_session(mapping=mapping(),session=session(),requested_scopes=("admin",),now_ns=500,current_revocation_epoch=1)
    assert result.allowed is False and result.effective_scopes==()
