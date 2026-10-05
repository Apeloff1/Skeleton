"""Cancellation-, deadline-, and budget-safe provider-neutral inference streams."""
from __future__ import annotations
import asyncio
from collections.abc import AsyncIterable, Callable
import time
from skeleton.providers.contract import ProviderDelta
from .provider_bridge import record_provider_delta, terminate_provider_failure
from .session import InferenceContractError, InferenceSession, ModelResult

class StreamDeadlineExceeded(InferenceContractError):
    def __init__(self,result:ModelResult):
        super().__init__("inference stream deadline exceeded"); self.result=result

class StreamBudgetExceeded(InferenceContractError):
    def __init__(self,result:ModelResult):
        super().__init__("inference stream budget exceeded"); self.result=result

async def consume_provider_stream(
    session:InferenceSession, stream:AsyncIterable[ProviderDelta], *, attempts:int=1,
    clock:Callable[[],float]=time.monotonic, started_at:float|None=None,
    max_events:int|None=None,
)->tuple[ProviderDelta,...]:
    if max_events is not None and (not isinstance(max_events,int) or isinstance(max_events,bool) or max_events<1):
        raise InferenceContractError("invalid stream event budget")
    start=clock() if started_at is None else started_at
    deadline=start+(session.request.deadline_ms/1000.0)
    collected=[]
    try:
        iterator=stream.__aiter__()
        while True:
            remaining=deadline-clock()
            if remaining<=0:
                if session._terminal is None:
                    result=terminate_provider_failure(session,reason="deadline",attempts=attempts)
                    raise StreamDeadlineExceeded(result)
                break
            if max_events is not None and len(collected)>=max_events:
                if session._terminal is None:
                    result=terminate_provider_failure(session,reason="provider_error",attempts=attempts)
                    raise StreamBudgetExceeded(result)
                break
            try:
                delta=await asyncio.wait_for(iterator.__anext__(),timeout=remaining)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                if session._terminal is None:
                    result=terminate_provider_failure(session,reason="deadline",attempts=attempts)
                    raise StreamDeadlineExceeded(result)
                break
            record_provider_delta(session,delta); collected.append(delta)
            if session._terminal is not None:
                break
    except asyncio.CancelledError:
        if session._terminal is None:
            terminate_provider_failure(session,reason="cancelled",attempts=attempts)
        raise
    return tuple(collected)
