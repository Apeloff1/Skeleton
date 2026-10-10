import pytest
from skeleton.ai.inbox_causality import InboundMessage,InboxLedger

def m(seq=0,epoch=1,p="p",causal=()): return InboundMessage.create("producer",epoch,seq,p,causal)

def test_message_identity_canonicalizes_causality():
 assert m(causal=("b","a"))==m(causal=("a","b"))

def test_sequence_gap_fails_closed():
 l=InboxLedger()
 with pytest.raises(PermissionError):l.admit(m(1))

def test_duplicate_message_returns_same_processing_receipt():
 l=InboxLedger();x=m();a=l.commit(x,"write:1",("effect:b","effect:a"));b=l.commit(x,"write:1",("effect:a","effect:b"));assert a==b

def test_duplicate_cannot_change_effects():
 l=InboxLedger();x=m();l.commit(x,"write:1")
 with pytest.raises(PermissionError):l.commit(x,"write:2")

def test_same_sequence_different_message_rejected():
 l=InboxLedger();l.commit(m(),"w")
 with pytest.raises(PermissionError):l.commit(m(p="different"),"w2")

def test_epoch_advance_resets_sequence_and_old_epoch_is_fenced():
 l=InboxLedger();l.commit(m(),"w");l.commit(m(0,2),"w2")
 with pytest.raises(PermissionError):l.admit(m(1,1))

def test_replay_window_rejects_ancient_sequence():
 l=InboxLedger(replay_window=2)
 for i in range(4):l.commit(m(i),f"w:{i}")
 with pytest.raises(PermissionError):l.admit(m(0,p="other"))

def test_processing_receipt_binds_effect_set():
 a=InboxLedger().commit(m(),"w",("e1",));b=InboxLedger().commit(m(),"w",("e2",));assert a.receipt_id!=b.receipt_id

def test_quarantine_is_deterministic_and_evidence_locked():
 l=InboxLedger();x=m();a=l.quarantine(x,"malformed-history","ev:1");assert a==l.quarantine(x,"malformed-history","ev:1")
 with pytest.raises(PermissionError):l.quarantine(x,"malformed-history","ev:2")

def test_duplicate_causal_identity_rejected():
 with pytest.raises(ValueError):m(causal=("a","a"))
