import pytest
from skeleton.ai.replication_protocol import ReplicatedEntry,AppendRequest,FollowerState,apply_append,SnapshotChunk,verify_snapshot_chunks

def e(i,t=1,s=None): return ReplicatedEntry(f"entry:{s or i}",i,t,f"payload:{s or i}")
def req(**kw):
 d=dict(leader_id="leader",term=2,prev_log_index=1,prev_log_term=1,entries=(e(2,2),),leader_commit=2);d.update(kw);return AppendRequest.create(**d)

def test_append_and_commit_propagation():
 s=FollowerState(1,(e(1),),0);n,r=apply_append(s,req());assert r.accepted and n.commit_index==2 and n.current_term==2

def test_stale_term_rejected_without_mutation():
 s=FollowerState(3,(e(1),),1);r=apply_append(s,req(term=2));assert not r.accepted

def test_missing_previous_returns_conflict_hint():
 s=FollowerState(1,(e(1),),0);r=apply_append(s,req(prev_log_index=3,prev_log_term=1,entries=()));assert not r.accepted and r.conflict_index==2

def test_previous_term_conflict_hint():
 s=FollowerState(2,(e(1),e(2,2),e(3,2)),1);r=apply_append(s,req(prev_log_index=3,prev_log_term=1,entries=()));assert not r.accepted and r.conflict_index==2 and r.conflict_term==2

def test_retransmission_is_idempotent():
 s=FollowerState(2,(e(1),e(2,2)),2);n,r=apply_append(s,req());assert n==s and r.accepted

def test_uncommitted_divergent_tail_replaced():
 s=FollowerState(2,(e(1),e(2,2,"old")),1);n,r=apply_append(s,req());assert n.entries[1].entry_id=="entry:2" and r.accepted

def test_committed_divergence_rejected():
 s=FollowerState(2,(e(1),e(2,2,"old")),2)
 with pytest.raises(PermissionError):apply_append(s,req())

def test_catchup_is_bounded():
 s=FollowerState(1,(e(1),),0);q=AppendRequest.create("leader",2,1,1,(e(2,2),e(3,2)),0)
 with pytest.raises(ValueError):apply_append(s,q,max_batch=1)

def test_noncontiguous_request_rejected():
 with pytest.raises(ValueError):AppendRequest.create("leader",2,1,1,(e(3,2),),0)

def test_snapshot_chunks_order_independent():
 cs=(SnapshotChunk("snap:1",0,2,"d0"),SnapshotChunk("snap:1",1,2,"d1"));assert verify_snapshot_chunks("snap:1",cs)==verify_snapshot_chunks("snap:1",tuple(reversed(cs)))

def test_snapshot_transfer_rejects_incomplete_or_foreign():
 with pytest.raises(ValueError):verify_snapshot_chunks("snap:1",(SnapshotChunk("snap:1",0,2,"d0"),))
 with pytest.raises(PermissionError):verify_snapshot_chunks("snap:1",(SnapshotChunk("snap:1",0,2,"d0"),SnapshotChunk("snap:2",1,2,"d1")))
