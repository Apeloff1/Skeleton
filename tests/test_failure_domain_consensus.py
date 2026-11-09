import pytest
from dataclasses import replace
from skeleton.ai.failure_domain_consensus import Replica,ConsensusConfig,elect,validate_leader,handoff,degraded_admissible,reconcile_terms

def cfg(**kw):
 rs=(Replica("r1","az-a",1),Replica("r2","az-b",1),Replica("r3","az-c",1),Replica("r4","az-a",1),Replica("r5","az-b",1))
 d=dict(cluster_id="c1",replicas=rs,quorum=3,min_failure_domains=2,degraded_quorum=3);d.update(kw);return ConsensusConfig(**d)

def test_config_identity_order_independent():
 x=cfg();assert x.config_id==cfg(replicas=tuple(reversed(x.replicas))).config_id

def test_nonmajority_quorum_rejected():
 with pytest.raises(ValueError):cfg(quorum=2)

def test_election_requires_failure_domain_diversity():
 x=cfg()
 with pytest.raises(PermissionError):elect(x,1,"r1",("r1","r4","r1"),100,200)
 with pytest.raises(PermissionError):elect(x,1,"r1",("r1","r4"),100,200)

def test_duplicate_voter_rejected():
 x=cfg()
 with pytest.raises(ValueError):elect(x,1,"r1",("r1","r2","r2"),100,200)

def test_term_and_expiry_fence_leader():
 x=cfg();l=elect(x,4,"r1",("r1","r2","r3"),100,200);assert validate_leader(x,l,4,150)
 with pytest.raises(PermissionError):validate_leader(x,l,3,150)
 with pytest.raises(PermissionError):validate_leader(x,l,4,200)

def test_live_leader_blocks_split_brain_handoff():
 x=cfg();l=elect(x,4,"r1",("r1","r2","r3"),100,200)
 with pytest.raises(PermissionError):handoff(x,l,5,"r2",("r1","r2","r3"),150,250)

def test_handoff_requires_higher_term_after_expiry():
 x=cfg();l=elect(x,4,"r1",("r1","r2","r3"),100,200)
 with pytest.raises(PermissionError):handoff(x,l,4,"r2",("r1","r2","r3"),200,300)
 n=handoff(x,l,5,"r2",("r1","r2","r3"),200,300);assert n.term==5

def test_degraded_mode_preserves_majority_and_domains():
 x=cfg();assert degraded_admissible(x,("r1","r2","r3"));assert not degraded_admissible(x,("r1","r4"));assert not degraded_admissible(x,("r1","r4","r9"))

def test_reconcile_selects_highest_term():
 x=cfg();a=elect(x,4,"r1",("r1","r2","r3"),100,150);b=elect(x,5,"r2",("r1","r2","r3"),150,250);assert reconcile_terms((a,b))==b

def test_reconcile_rejects_same_term_split_brain():
 x=cfg();a=elect(x,4,"r1",("r1","r2","r3"),100,200);b=replace(a,leader_id="r2")
 with pytest.raises(PermissionError):reconcile_terms((a,b))

def test_reconcile_rejects_cross_config():
 a=cfg();b=cfg(cluster_id="c2");la=elect(a,1,"r1",("r1","r2","r3"),100,200);lb=elect(b,2,"r1",("r1","r2","r3"),100,200)
 with pytest.raises(PermissionError):reconcile_terms((la,lb))
