import pytest
from skeleton.foundation.resource_namespace import *
def n(x):return ResourceName(x)
def test_scope_includes_tenant_project_version():
 r=ResourceNamespace(n("tenant"),n("project"),n("v1")).resolve(n("model"));assert r.canonical()=="res1:tenant:project:v1:model"
def test_canonical_roundtrip():
 raw="res1:t:p:v1:item";assert parse_resource_ref(raw).canonical()==raw
@pytest.mark.parametrize("bad",["..","a..b","../x","Ａ","a/b","A"," a"])
def test_traversal_confusable_or_ambiguous_names_rejected(bad):
 with pytest.raises(ValueError):n(bad)
def test_ambiguous_reference_shape_rejected():
 with pytest.raises(ValueError):parse_resource_ref("res1:t:p:item")
