"""Replay verification for deterministic inference receipts."""
from __future__ import annotations
import hmac
from dataclasses import dataclass
from .session import InferenceContractError, InferenceSession, ModelRequest, ModelResult, ModelStreamEvent

@dataclass(frozen=True)
class InferenceReplay:
    request:ModelRequest
    events:tuple[ModelStreamEvent,...]
    expected_result_digest:str
    def __post_init__(self):
        if not isinstance(self.request,ModelRequest): raise InferenceContractError("ModelRequest required")
        if not isinstance(self.events,tuple) or not self.events: raise InferenceContractError("non-empty event tuple required")
        if not isinstance(self.expected_result_digest,str) or len(self.expected_result_digest)!=64: raise InferenceContractError("invalid expected result digest")

def verify_replay(replay:InferenceReplay,result:ModelResult)->bool:
    if not isinstance(replay,InferenceReplay) or not isinstance(result,ModelResult): raise InferenceContractError("typed replay and result required")
    if replay.request.operation_id!=result.operation_id or replay.request.request_digest!=result.request_digest: raise InferenceContractError("cross-request replay")
    if replay.request.provider!=result.provider or replay.request.model!=result.model: raise InferenceContractError("replay provider identity mismatch")
    session=InferenceSession(replay.request)
    for event in replay.events: session.record(event)
    if not hmac.compare_digest(session.event_chain_digest,result.event_chain_digest): raise InferenceContractError("replay event chain mismatch")
    if not hmac.compare_digest(replay.expected_result_digest,result.result_digest): raise InferenceContractError("replay result mismatch")
    return True
