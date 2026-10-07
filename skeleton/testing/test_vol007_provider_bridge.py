import pytest
from skeleton.inference import *
from skeleton.inference.provider_bridge import *
from skeleton.provider_runtime import ProviderResponse, provider_response_deltas
from skeleton.providers.contract import ProviderUsage
H="a"*64
def request(): return ModelRequest("op",H,"m","p",64,1000)
def response():
    return ProviderResponse(text="ok",provider="p",model="m",response_id="r",usage=ProviderUsage(input_tokens=2,output_tokens=3))
def test_real_provider_projection_yields_bound_result():
    s=InferenceSession(request()); consume_provider_deltas(s,provider_response_deltas(response())); r=finish_provider_response(s,response(),attempts=2)
    assert r.terminal_reason=="completed" and r.usage==InferenceUsage(2,3,2)
def test_provider_identity_substitution_denied():
    s=InferenceSession(request()); consume_provider_deltas(s,provider_response_deltas(response()))
    bad=ProviderResponse(text="ok",provider="evil",model="m",usage=ProviderUsage())
    with pytest.raises(InferenceContractError): finish_provider_response(s,bad)
def test_missing_terminal_delta_cannot_publish_success():
    s=InferenceSession(request())
    ds=provider_response_deltas(response())
    consume_provider_deltas(s,ds[:-1])
    with pytest.raises(InferenceContractError): finish_provider_response(s,response())
def test_delta_reorder_and_duplicate_fail_closed():
    ds=provider_response_deltas(response()); s=InferenceSession(request())
    with pytest.raises(InferenceContractError): record_provider_delta(s,ds[1])
    s=InferenceSession(request()); record_provider_delta(s,ds[0])
    with pytest.raises(InferenceContractError): record_provider_delta(s,ds[0])
def test_failure_receipts_never_publish_response():
    for reason in ("cancelled","deadline","provider_error","policy_denied"):
        r=terminate_provider_failure(InferenceSession(request()),reason=reason)
        assert r.terminal_reason==reason and r.response_digest is None
def test_provider_payload_digest_detects_tamper():
    a=response(); b=ProviderResponse(text="changed",provider="p",model="m",response_id="r",usage=a.usage)
    assert provider_payload_digest(a)!=provider_payload_digest(b)
