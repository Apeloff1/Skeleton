import pytest
from dataclasses import replace
from skeleton.inference import *
from skeleton.inference.replay import InferenceReplay,verify_replay
H="a"*64
def fixture():
    q=ModelRequest("op",H,"m","p",64,1000); s=InferenceSession(q)
    es=(ModelStreamEvent(0,"text","b"*64),ModelStreamEvent(1,"final","c"*64))
    for e in es:s.record(e)
    r=s.finish(reason="completed",usage=InferenceUsage(1,2,1),response_digest="d"*64)
    return q,es,r
def test_exact_replay_verifies():
    q,e,r=fixture(); assert verify_replay(InferenceReplay(q,e,r.result_digest),r)
def test_truncated_replay_fails_closed():
    q,e,r=fixture()
    with pytest.raises(InferenceContractError): verify_replay(InferenceReplay(q,e[:-1],r.result_digest),r)
def test_tampered_payload_fails_closed():
    q,e,r=fixture(); bad=(replace(e[0],payload_digest="e"*64),e[1])
    with pytest.raises(InferenceContractError): verify_replay(InferenceReplay(q,bad,r.result_digest),r)
def test_reordered_replay_fails_closed():
    q,e,r=fixture()
    with pytest.raises(InferenceContractError): verify_replay(InferenceReplay(q,(e[1],e[0]),r.result_digest),r)
def test_cross_operation_replay_denied():
    q,e,r=fixture(); q2=replace(q,operation_id="other")
    with pytest.raises(InferenceContractError): verify_replay(InferenceReplay(q2,e,r.result_digest),r)
def test_result_usage_tamper_detected():
    q,e,r=fixture(); bad=replace(r,usage=InferenceUsage(9,9,1))
    with pytest.raises(InferenceContractError): verify_replay(InferenceReplay(q,e,r.result_digest),bad)
