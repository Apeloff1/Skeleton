import pytest
from skeleton.ai.resource_resolution import *
R=[{"tenant":"t","project":"p","name":"x","version":"v1","lifecycle":"active"},{"tenant":"t","project":"p","name":"x","version":"v2","lifecycle":"active"}]
def test_unauthorized_resolution_fails_closed():
 with pytest.raises(PermissionError):resolve_resource(ResourceQuery("t","p","x","v1"),R,authorized=False)
def test_latest_alias_is_explicit_and_traceable():
 h,r=resolve_resource(ResourceQuery("t","p","x",None),R,authorized=True);assert h.canonical_ref.endswith(":v2:x") and r.alias_used
def test_cross_tenant_not_returned():
 with pytest.raises(KeyError):resolve_resource(ResourceQuery("other","p","x","v1"),R,authorized=True)

def test_latest_alias_orders_numeric_versions_naturally():
 reg=({"tenant":"t","project":"p","name":"n","version":"v2","lifecycle":"active"},{"tenant":"t","project":"p","name":"n","version":"v10","lifecycle":"active"})
 h,r=resolve_resource(ResourceQuery("t","p","n",None),reg,authorized=True);assert ":v10:" in h.canonical_ref and r.alias_used

def test_malformed_registry_fails_closed():
 import pytest
 with pytest.raises(ValueError):resolve_resource(ResourceQuery("t","p","n",None),({"tenant":"t"},),authorized=True)
