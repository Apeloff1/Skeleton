from skeleton.data.locality import *
def test_locality_never_overrides_security_region():assert not plan_transfer(DataLocation("a",1,"secret"),"b",LocalityConstraint(frozenset({"a"}),5),1).allowed
def test_stale_local_copy_not_preferred():assert not plan_transfer(DataLocation("a",10,"x"),"a",LocalityConstraint(frozenset({"a"}),5),0).allowed
