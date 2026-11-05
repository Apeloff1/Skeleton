"""Stable resource-bound worker selection, no GPU capability inference from labels."""
from __future__ import annotations
from dataclasses import dataclass
from .workers import Worker,WorkerError

@dataclass(frozen=True,slots=True)
class PlacementRequest:
    model_sha:str
    tokenizer_sha:str
    estimated_context_tokens:int
    reserved_memory_bytes:int
    deadline_ns:int
    request_id:str

@dataclass(frozen=True,slots=True)
class PlacementDecision:
    accepted:bool
    reason:str
    worker_id:str|None
    epoch:int|None
    remaining_tokens:int|None


def place(request:PlacementRequest,workers:tuple[Worker,...])->PlacementDecision:
    if type(request.estimated_context_tokens) is not int or not 1<=request.estimated_context_tokens<=131072:
        raise WorkerError('invalid model context reservation')
    if type(request.reserved_memory_bytes) is not int or request.reserved_memory_bytes<0:
        raise WorkerError('invalid memory reservation')
    candidates=[w for w in workers if w.state=='ready' and w.model_sha==request.model_sha
        and w.tokenizer_sha==request.tokenizer_sha
        and w.capacity_tokens-w.active_tokens>=request.estimated_context_tokens
        and w.memory_headroom_bytes>=request.reserved_memory_bytes]
    if not candidates:return PlacementDecision(False,'no-eligible-local-worker',None,None,None)
    candidates.sort(key=lambda w:(w.active_tokens/w.capacity_tokens if w.capacity_tokens else 1,
                                  -(w.capacity_tokens-w.active_tokens),w.worker_id))
    chosen=candidates[0]
    return PlacementDecision(True,'pinned-local-worker',chosen.worker_id,chosen.epoch,
        chosen.capacity_tokens-chosen.active_tokens-request.estimated_context_tokens)
