"""Bridge canonical provider deltas/responses into deterministic inference receipts."""
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Iterable
from skeleton.provider_runtime import ProviderResponse
from skeleton.providers.contract import ProviderDelta, ProviderDeltaKind
from .session import InferenceContractError, InferenceSession, InferenceUsage, ModelRequest, ModelResult, ModelStreamEvent

def _plain(v:Any):
    if isinstance(v,Enum): return v.value
    if is_dataclass(v): return _plain(asdict(v))
    if isinstance(v,dict): return {str(k):_plain(x) for k,x in sorted(v.items(),key=lambda p:str(p[0]))}
    if isinstance(v,(list,tuple)): return [_plain(x) for x in v]
    if v is None or isinstance(v,(str,int,float,bool)): return v
    raise InferenceContractError("provider payload is not canonically serializable")
def provider_payload_digest(v:Any)->str:
    return sha256(json.dumps(_plain(v),sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

_KIND={"text":"text","structured":"structured","tool_call":"tool_call","usage":"usage","final":"final"}
def record_provider_delta(session:InferenceSession,delta:ProviderDelta)->str:
    if not isinstance(session,InferenceSession) or not isinstance(delta,ProviderDelta): raise InferenceContractError("typed session and ProviderDelta required")
    raw=delta.kind.value if isinstance(delta.kind,Enum) else str(delta.kind)
    kind=_KIND.get(raw)
    if kind is None: raise InferenceContractError("unsupported provider delta kind")
    # Provider sequence must agree with inference sequence; no silent renumbering.
    if delta.sequence!=len(session._events): raise InferenceContractError("provider delta sequence mismatch")
    return session.record(ModelStreamEvent(delta.sequence,kind,provider_payload_digest(delta)))

def consume_provider_deltas(session:InferenceSession,deltas:Iterable[ProviderDelta])->str:
    for delta in deltas: record_provider_delta(session,delta)
    return session.event_chain_digest

def finish_provider_response(session:InferenceSession,response:ProviderResponse,*,attempts:int=1)->ModelResult:
    if not isinstance(response,ProviderResponse): raise InferenceContractError("ProviderResponse required")
    if response.provider!=session.request.provider or response.model!=session.request.model: raise InferenceContractError("provider response identity mismatch")
    if session._terminal!="final": raise InferenceContractError("provider stream did not terminate successfully")
    usage=response.usage
    input_tokens=getattr(usage,"input_tokens",getattr(usage,"prompt_tokens",0)) or 0
    output_tokens=getattr(usage,"output_tokens",getattr(usage,"completion_tokens",0)) or 0
    receipt_usage=InferenceUsage(int(input_tokens),int(output_tokens),attempts)
    return session.finish(reason="completed",usage=receipt_usage,response_digest=provider_payload_digest(response))

def terminate_provider_failure(session:InferenceSession,*,reason:str,attempts:int=1)->ModelResult:
    if reason not in {"cancelled","deadline","provider_error","policy_denied"}: raise InferenceContractError("invalid failure reason")
    kind="cancelled" if reason=="cancelled" else "error"
    session.record(ModelStreamEvent(len(session._events),kind,provider_payload_digest({"reason":reason})))
    return session.finish(reason=reason,usage=InferenceUsage(attempts=attempts))
