import pytest
from dataclasses import replace
from skeleton.ai.replicated_log_integrity import ReplicatedLog,LogEntry,Snapshot,common_prefix,replay_digest

def log():
 l=ReplicatedLog();a=l.append(1,"cmd:a");b=l.append(1,"cmd:b");return l,a,b

def test_log_chain_and_identity_are_deterministic():
 l,a,b=log();assert b.previous_entry_id==a.entry_id;assert LogEntry.create(1,1,"cmd:a",None)==a

def test_term_regression_rejected():
 l,_,_=log()
 with pytest.raises(PermissionError):l.append(0,"cmd:c")

def test_commit_index_is_monotonic_and_bounded():
 l,_,_=log();l.commit(1)
 with pytest.raises(PermissionError):l.commit(0)
 with pytest.raises(PermissionError):l.commit(3)

def test_committed_history_cannot_be_truncated():
 l,_,_=log();l.commit(1)
 with pytest.raises(PermissionError):l.truncate_uncommitted(1)
 l.truncate_uncommitted(2);assert l.last_index==1

def test_import_rejects_tampered_entry():
 l,a,_=log()
 with pytest.raises(ValueError):ReplicatedLog((replace(a,command_digest="cmd:x"),))

def test_common_prefix_detects_divergent_tail():
 a,_,_=log();b=ReplicatedLog();b.append(1,"cmd:a");b.append(2,"cmd:x");assert common_prefix(a,b)==1

def test_snapshot_install_compacts_prefix_and_advances_commit():
 l,a,b=log();s=Snapshot.create(2,1,b.entry_id,"state:2");l.install_snapshot(s);assert l.last_index==2;assert l.commit_index==2;assert l.entries()==()

def test_snapshot_conflict_rejected():
 l,a,b=log();s=Snapshot.create(2,2,b.entry_id,"state:x")
 with pytest.raises(PermissionError):l.install_snapshot(s)

def test_snapshot_cannot_move_behind_commit():
 l,a,b=log();l.commit(2);s=Snapshot.create(1,1,a.entry_id,"state:1")
 with pytest.raises(PermissionError):l.install_snapshot(s)

def test_replay_is_deterministic():
 l,_,_=log();assert replay_digest(None,l.entries())==replay_digest(None,l.entries())

def test_snapshot_replay_continues_from_compacted_state():
 l,a,b=log();s=Snapshot.create(1,1,a.entry_id,"state:1");assert replay_digest(s,(b,)).startswith("state-replay-sha256:")
