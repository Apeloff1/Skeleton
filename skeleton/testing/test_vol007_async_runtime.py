import asyncio, pytest
from skeleton.inference import *
from skeleton.inference.async_runtime import consume_provider_stream,StreamDeadlineExceeded,StreamBudgetExceeded
from skeleton.providers.contract import ProviderDelta,ProviderDeltaKind
H="a"*64
def q(deadline=1000): return ModelRequest("op",H,"m","p",64,deadline)
@pytest.mark.asyncio
async def test_cancellation_becomes_terminal_and_propagates():
    s=InferenceSession(q())
    async def stream():
        yield ProviderDelta(sequence=0,kind=ProviderDeltaKind.TEXT,text="x")
        raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError): await consume_provider_stream(s,stream())
    assert s._terminal=="cancelled"
@pytest.mark.asyncio
async def test_completed_stream_is_not_reclassified():
    s=InferenceSession(q())
    async def stream():
        yield ProviderDelta(sequence=0,kind=ProviderDeltaKind.FINAL)
        yield ProviderDelta(sequence=1,kind=ProviderDeltaKind.TEXT,text="late")
    out=await consume_provider_stream(s,stream())
    assert len(out)==1 and s._terminal=="final"
@pytest.mark.asyncio
async def test_deadline_produces_replayable_non_success_receipt():
    s=InferenceSession(q(1))
    async def stream():
        await asyncio.sleep(.02)
        yield ProviderDelta(sequence=0,kind=ProviderDeltaKind.TEXT,text="late")
    with pytest.raises(StreamDeadlineExceeded) as exc: await consume_provider_stream(s,stream())
    assert exc.value.result.terminal_reason=="deadline" and exc.value.result.response_digest is None
@pytest.mark.asyncio
async def test_event_budget_stops_before_excess_provider_output():
    s=InferenceSession(q())
    async def stream():
        yield ProviderDelta(sequence=0,kind=ProviderDeltaKind.TEXT,text="a")
        yield ProviderDelta(sequence=1,kind=ProviderDeltaKind.TEXT,text="b")
    with pytest.raises(StreamBudgetExceeded) as exc: await consume_provider_stream(s,stream(),max_events=1)
    assert exc.value.result.response_digest is None and s._terminal=="error"
@pytest.mark.asyncio
async def test_invalid_budget_rejected_before_stream_consumption():
    s=InferenceSession(q())
    async def stream():
        yield ProviderDelta(sequence=0,kind=ProviderDeltaKind.FINAL)
    with pytest.raises(InferenceContractError): await consume_provider_stream(s,stream(),max_events=0)
