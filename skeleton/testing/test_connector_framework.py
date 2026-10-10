from __future__ import annotations
import hashlib,pytest
from skeleton.connectors.framework import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
D=ConnectorDefinition("CONNECTOR.1",S("schema"),frozenset({Scope.READ}),100,60)
def test_discovery_definition_contains_no_credentials():assert not hasattr(D,"credential_ref")
def test_session_uses_opaque_credential_reference():assert open_session(D,ConnectorSession("SESSION.1","CONNECTOR.1",frozenset({Scope.READ}),"secret://connector/1"))
def test_write_scope_cannot_self_authorize():
 with pytest.raises(ConnectorError,match="scope"):open_session(D,ConnectorSession("SESSION.1","CONNECTOR.1",frozenset({Scope.WRITE}),"secret://connector/1"))
def test_page_limit_enforced():
 with pytest.raises(ConnectorError,match="page"):validate_page(D,ConnectorResult("SESSION.1",tuple(range(101)),None))
def test_error_semantics_do_not_mix_partial_data():
 with pytest.raises(ConnectorError,match="error"):validate_page(D,ConnectorResult("SESSION.1",("leak",),None,"AUTH_DENIED"))
