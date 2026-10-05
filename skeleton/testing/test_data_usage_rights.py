from skeleton.data.usage_rights import *
def test_training_requires_training_grant():assert not decide(DataRights("d",(UsageGrant("eval",frozenset({"NO"}),10,False),)),"eval","NO",1,True).allowed
def test_derivative_preserves_rights_lineage():assert derive(DataRights("d",()),"x").lineage==("d",)

def test_negative_time_denied_and_self_derivation_rejected():
 import pytest
 r=DataRights("d",(UsageGrant("eval",frozenset({"NO"}),10,False),))
 assert not decide(r,"eval","NO",-1).allowed
 with pytest.raises(ValueError):derive(r,"d")
