import pytest
from skeleton.ai.read_consistency import ReadIndexProof,LeaderLease,FreshnessToken,linearizable_read,lease_read,follower_read

def proof(): return ReadIndexProof.create("c",4,20,"l",("a","b","c"),2)
def lease(): return LeaderLease("lease:1","c",4,"l",20,100,300,20)

def test_read_index_proof_is_canonical():
 assert proof()==ReadIndexProof.create("c",4,20,"l",("c","a","b"),2)

def test_read_index_requires_unique_quorum():
 with pytest.raises(ValueError):ReadIndexProof.create("c",4,20,"l",("a","a"),2)

def test_linearizable_read_rejects_stale_term_or_unapplied_index():
 with pytest.raises(PermissionError):linearizable_read(proof(),3,20,"s")
 with pytest.raises(PermissionError):linearizable_read(proof(),4,19,"s")

def test_linearizable_read_preserves_monotonic_session():
 with pytest.raises(PermissionError):linearizable_read(proof(),4,20,"s",21)
 assert linearizable_read(proof(),4,20,"s",20).read_index==20

def test_lease_read_uses_clock_skew_reduced_window():
 assert lease_read(lease(),4,20,279,"s").mode=="lease"
 with pytest.raises(PermissionError):lease_read(lease(),4,20,280,"s")

def test_lease_read_rejects_preissue_clock_and_stale_term():
 with pytest.raises(PermissionError):lease_read(lease(),4,20,99,"s")
 with pytest.raises(PermissionError):lease_read(lease(),5,20,150,"s")

def test_follower_read_enforces_staleness_and_term():
 t=FreshnessToken.create("c",4,18,100)
 assert follower_read(t,"c",4,50,150,"s").read_index==18
 with pytest.raises(PermissionError):follower_read(t,"c",4,49,150,"s")
 with pytest.raises(PermissionError):follower_read(t,"c",5,50,150,"s")

def test_follower_read_rejects_clock_reversal_and_session_regression():
 t=FreshnessToken.create("c",4,18,100)
 with pytest.raises(PermissionError):follower_read(t,"c",4,50,99,"s")
 with pytest.raises(PermissionError):follower_read(t,"c",4,50,120,"s",19)

def test_receipts_bind_session_identity():
 a=linearizable_read(proof(),4,20,"s1");b=linearizable_read(proof(),4,20,"s2");assert a.receipt_id!=b.receipt_id
