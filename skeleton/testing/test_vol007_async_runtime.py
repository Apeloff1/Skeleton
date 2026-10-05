import asyncio, pytest
from skeleton.inference import *
from skeleton.inference.async_runtime import consume_provider_stream
from skeleton.providers.contract import ProviderDelta,ProviderDeltaKind
H="a"*64
def q(): return ModelRequest("op",H,"m","p",64,1000)
@pytest.mark.asyncio
async def test_cancellation_becomes_terminal_and_propagates():
    s=InferenceSession(q())
    async def stream():
        yield ProviderDelta(sequence=0,kind=ProviderDeltaKind.TEXT,text="x")
        raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError): await consume_provider_stream(s,stream())
    assert s._terminal=="cancelled"
    with pytest.raises(InferenceContractError): s.record(ModelStreamEvent(2,"text",H))
@pytest.mark.asyncio
async def test_completed_stream_is_not_reclassified():
    s=InferenceSession(q())
    async def stream():
        yield ProviderDelta(sequence=0,kind=ProviderDeltaKind.FINAL)
    out=await consume_provider_stream(s,stream())
    assert len(out)==1 and s._terminal=="final"
