from skeleton.data.locality import *
def test_locality_never_overrides_security_region():assert not plan_transfer(DataLocation("a",1,"secret"),"b",LocalityConstraint(frozenset({"a"}),5),1).allowed
def test_stale_local_copy_not_preferred():assert not plan_transfer(DataLocation("a",10,"x"),"a",LocalityConstraint(frozenset({"a"}),5),0).allowed

def test_region_allowed_but_classification_denied():
 s=DataLocation("NO",0,"secret");c=LocalityConstraint(frozenset({"NO"}),10,frozenset({"public"}));assert not plan_transfer(s,"NO",c,1).allowed
