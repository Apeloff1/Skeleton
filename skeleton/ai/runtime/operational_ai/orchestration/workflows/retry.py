"""Deterministic jittered retry policy; no retries for uncertain side effects."""
from __future__ import annotations
from hashlib import sha256
from .graph import WorkflowError

_RETRYABLE={'backend-unavailable','resource-pressure','temporary-read','admission-timeout'}


def delay_ms(*,operation:str,attempt:int,reason:str,base_ms:int=100,
             ceiling_ms:int=30_000)->int|None:
    if type(attempt) is not int or not 1<=attempt<=16 or type(base_ms) is not int or base_ms<1:
        raise WorkflowError('invalid retry attempt')
    if reason not in _RETRYABLE:return None
    if ceiling_ms<base_ms or ceiling_ms>600_000:raise WorkflowError('invalid retry ceiling')
    raw=sha256(f'{operation}:{attempt}:{reason}'.encode()).digest()
    jitter=int.from_bytes(raw[:4],'big')%base_ms
    return min(ceiling_ms,base_ms*(2**(attempt-1))+jitter)
