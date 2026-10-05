"""Cancellation-safe execution wrapper for provider-neutral inference streams."""
from __future__ import annotations
import asyncio
from typing import AsyncIterable
from skeleton.providers.contract import ProviderDelta
from .provider_bridge import record_provider_delta, terminate_provider_failure
from .session import InferenceSession, InferenceUsage, ModelResult

async def consume_provider_stream(session:InferenceSession,stream:AsyncIterable[ProviderDelta],*,attempts:int=1)->tuple[ProviderDelta,...]:
    collected=[]
    try:
        async for delta in stream:
            record_provider_delta(session,delta); collected.append(delta)
    except asyncio.CancelledError:
        # Cancellation is evidence-bearing and terminal, but cancellation itself
        # must still propagate to the scheduler/caller; it is never retryable here.
        if session._terminal is None:
            terminate_provider_failure(session,reason="cancelled",attempts=attempts)
        raise
    return tuple(collected)
