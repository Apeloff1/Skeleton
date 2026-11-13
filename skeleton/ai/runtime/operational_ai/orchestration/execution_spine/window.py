"""Loss-accountable deterministic context window, preserving complete disk history.

Never replaces omitted turns with an LLM-invented summary. Every removal is
recorded as an explicit count; the full original history remains durable and
retrievable from the authoritative transcript store.
"""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import SpineError,SpineLimits,canonical

@dataclass(frozen=True,slots=True)
class Window:
    messages:tuple[dict,...]
    retained_turns:int
    omitted_turns:int
    retained_bytes:int
    status:str='loss-accounted-window-not-full-history'

def plan(history:tuple[dict,...],limits:SpineLimits,*,reserve_bytes:int=2048)->Window:
    if type(reserve_bytes)is not int or not 0<=reserve_bytes<=32768:
        raise SpineError('invalid context reservation')
    if len(history)%2 or len(history)>2*limits.max_history:
        raise SpineError('untrusted history span')
    # Reserve for current user, system instructions, evidence, and output.
    available=max(0,3*(limits.context_tokens-limits.max_output_tokens)-reserve_bytes)
    if available<=0:raise SpineError('no room for current inference context')
    selected=[];used=0
    for i in range(len(history)-2,-1,-2):
        pair=(history[i],history[i+1])
        raw=canonical(list(pair),ceiling=2_097_152)
        if used+len(raw)>available:break
        used+=len(raw);selected[0:0]=pair
    result=tuple(selected)
    return Window(result,len(result)//2,len(history)//2-len(result)//2,used)
