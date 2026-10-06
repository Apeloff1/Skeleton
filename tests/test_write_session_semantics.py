import pytest
from skeleton.ai.write_session_semantics import CausalToken,WriteIntent,WriteLedger

def w(**kw):
 d=dict(stream_id="s",session_id="sess",session_sequence=1,idempotency_key="idem:1",expected_revision=0,payload_digest="payload:1",causal_tokens=());d.update(kw);return WriteIntent.create(**d)

def test_intent_canonicalizes_causal_tokens():
 a=CausalToken.create("a",2);b=CausalToken.create("b",3);assert w(causal_tokens=(a,b))==w(causal_tokens=(b,a))

def test_compare_and_swap_fails_closed():
 with pytest.raises(PermissionError):WriteLedger().apply(w(),1,5,{})

def test_exact_retry_returns_same_receipt():
 l=WriteLedger();i=w();a=l.apply(i,0,5,{});b=l.apply(i,0,5,{});assert a==b

def test_idempotency_key_cannot_change_effect():
 l=WriteLedger();l.apply(w(),0,5,{})
 with pytest.raises(PermissionError):l.apply(w(payload_digest="payload:2"),0,6,{})

def test_session_sequence_is_monotonic():
 l=WriteLedger();l.apply(w(),0,5,{})
 with pytest.raises(PermissionError):l.apply(w(idempotency_key="idem:2",payload_digest="p2"),1,6,{})

def test_same_sequence_cannot_bind_different_intent():
 l=WriteLedger();l.apply(w(),0,5,{})
 with pytest.raises(PermissionError):l.apply(w(idempotency_key="idem:2",payload_digest="different"),1,6,{})

def test_next_session_sequence_commits_next_revision():
 l=WriteLedger();l.apply(w(),0,5,{});r=l.apply(w(session_sequence=2,idempotency_key="idem:2",expected_revision=1,payload_digest="p2"),1,6,{});assert r.revision==2

def test_causal_dependency_must_be_visible():
 t=CausalToken.create("other",4);i=w(causal_tokens=(t,))
 with pytest.raises(PermissionError):WriteLedger().apply(i,0,5,{"other":3})
 assert WriteLedger().apply(i,0,5,{"other":4}).revision==1

def test_duplicate_causal_stream_rejected():
 a=CausalToken.create("x",1);b=CausalToken.create("x",2)
 with pytest.raises(ValueError):w(causal_tokens=(a,b))

def test_receipt_binds_log_index():
 a=WriteLedger().apply(w(),0,5,{});b=WriteLedger().apply(w(),0,6,{});assert a.receipt_id!=b.receipt_id
