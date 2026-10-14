import pytest
from skeleton.ai.membership_reconfiguration import Member,Membership,plan_reconfiguration,acknowledge,decide,rollback_plan,drain_safe

def old():
 return Membership("c1",7,(Member("a",1,"z1"),Member("b",1,"z2"),Member("c",1,"z3")))
def new():
 return Membership("c1",8,(Member("a",1,"z1"),Member("b",1,"z2"),Member("d",2,"z3")))

def test_membership_identity_order_independent():
 x=old();assert x.membership_id==Membership("c1",7,tuple(reversed(x.members))).membership_id

def test_epoch_must_advance_exactly_once():
 with pytest.raises(PermissionError):plan_reconfiguration(old(),Membership("c1",9,new().members),"op")

def test_generation_regression_rejected():
 bad=Membership("c1",8,(Member("a",0,"z1"),Member("b",1,"z2"),Member("d",2,"z3")))
 with pytest.raises(PermissionError):plan_reconfiguration(old(),bad,"op")

def test_joint_consensus_requires_majority_of_both_sets():
 o,n=old(),new();p=plan_reconfiguration(o,n,"op")
 a=acknowledge(p,o,n,"a",1,"e:a");b=acknowledge(p,o,n,"b",1,"e:b")
 assert decide(p,o,n,(a,b)).decision=="commit"
 assert decide(p,o,n,(a,)).decision=="pending"

def test_new_only_votes_do_not_satisfy_old_majority():
 o,n=old(),new();p=plan_reconfiguration(o,n,"op");d=acknowledge(p,o,n,"d",2,"e:d")
 assert decide(p,o,n,(d,)).decision=="pending"

def test_stale_generation_and_foreign_voter_rejected():
 o,n=old(),new();p=plan_reconfiguration(o,n,"op")
 with pytest.raises(PermissionError):acknowledge(p,o,n,"d",1,"e")
 with pytest.raises(PermissionError):acknowledge(p,o,n,"x",1,"e")

def test_duplicate_ack_rejected():
 o,n=old(),new();p=plan_reconfiguration(o,n,"op");a=acknowledge(p,o,n,"a",1,"e:a")
 with pytest.raises(ValueError):decide(p,o,n,(a,a))

def test_rollback_is_forward_epoch_not_history_rewrite():
 o,n=old(),new();p=plan_reconfiguration(o,n,"op");r=rollback_plan(p,o,n,"rollback:1");assert r.from_epoch==8;assert r.to_epoch==9

def test_drain_preserves_majority_and_failure_domains():
 x=Membership("c",1,(Member("a",1,"z1"),Member("b",1,"z2"),Member("c",1,"z3"),Member("d",1,"z1"),Member("e",1,"z2")))
 assert drain_safe(x,("e",),("a","b","c","d"))
 assert not drain_safe(x,("c","d","e"),("a","b"))
 assert not drain_safe(x,("b","c","e"),("a","d"))
