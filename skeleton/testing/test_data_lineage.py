import pytest
from skeleton.data.lineage_governance import *
def test_laundering_and_trust_upgrade_fail():
 g=GovernedLineage(); g.register(LineageAsset("raw","confidential","untrusted"))
 with pytest.raises(LineageGovernanceError): g.transform(transformation_id="t",version="1",environment_digest="a"*64,inputs=["raw"],outputs=["x"],classification="internal",trust="trusted")
def test_deletion_propagates():
 g=GovernedLineage(); g.register(LineageAsset("a","internal","trusted")); g.transform(transformation_id="ab",version="1",environment_digest="a"*64,inputs=["a"],outputs=["b"],classification="internal",trust="trusted"); g.transform(transformation_id="bc",version="1",environment_digest="b"*64,inputs=["b"],outputs=["c"],classification="internal",trust="trusted"); assert g.mark_deleted("a")==("a","b","c")
