import pytest
from skeleton.inference.session import *
H="a"*64
def req(): return ModelRequest("op",H,"model","provider",128,1000)
def test_deterministic_stream_receipt_and_usage():
    a=InferenceSession(req()); b=InferenceSession(req())
    for s,k in [(0,"text"),(1,"usage"),(2,"final")]:
        e=ModelStreamEvent(s,k,H); a.record(e); b.record(e)
    x=a.finish(reason="completed",usage=InferenceUsage(2,3,1),response_digest="b"*64); y=b.finish(reason="completed",usage=InferenceUsage(2,3,1),response_digest="b"*64)
    assert x==y and x.result_digest==y.result_digest
def test_noncontiguous_and_post_terminal_events_denied():
    s=InferenceSession(req())
    with pytest.raises(InferenceContractError): s.record(ModelStreamEvent(1,"text",H))
    s.record(ModelStreamEvent(0,"cancelled",H))
    with pytest.raises(InferenceContractError): s.record(ModelStreamEvent(1,"text",H))
def test_cancelled_cannot_publish_response():
    s=InferenceSession(req()); s.record(ModelStreamEvent(0,"cancelled",H))
    with pytest.raises(InferenceContractError): s.finish(reason="cancelled",usage=InferenceUsage(),response_digest=H)
def test_terminal_reason_must_match_stream():
    s=InferenceSession(req()); s.record(ModelStreamEvent(0,"final",H))
    with pytest.raises(InferenceContractError): s.finish(reason="provider_error",usage=InferenceUsage(),response_digest=H)
def test_retry_and_event_bounds_fail_closed():
    with pytest.raises(InferenceContractError): InferenceUsage(attempts=MAX_ATTEMPTS+1)
    with pytest.raises(InferenceContractError): ModelStreamEvent(MAX_EVENTS,"text",H)
def test_authority_escalation_denied():
    with pytest.raises(InferenceContractError): ModelResult("op",H,"p","m","completed",InferenceUsage(),H,H,"execution")
