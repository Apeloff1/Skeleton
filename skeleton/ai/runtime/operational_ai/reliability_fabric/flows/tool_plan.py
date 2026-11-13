"""Read-only tool-intent plan with exact signed grant, no direct tool execution."""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
from ..contracts import fail
from skeleton.ai.runtime.operational_ai.trust_gates.control.tool_intents import ToolIntents

@dataclass(frozen=True,slots=True)
class IntentProof:
    request_id:str
    intent_id:str
    state:str
    tool:str
    result_sha256:str|None=None

class ToolPlan:
    def __init__(self,maximum=128):
        self._state=ToolIntents(maximum=maximum)
        self._lock=RLock()
        self._prepared={}

    def prepare(self,*,request_id,intent_id,grant,call):
        if type(request_id) is not str or not request_id or len(request_id)>96:
            fail("invalid tool request identity")
        if type(call) is not dict or call.get("request_id")!=request_id:
            fail("tool call is not bound to parent request")
        result=self._state.prepare(id=intent_id,grant=grant,call=call)
        with self._lock:
            self._prepared[intent_id]=(request_id,grant["tool_id"])
        return IntentProof(request_id,intent_id,result["state"],grant["tool_id"])

    def settle(self,*,request_id,intent_id,result_sha256,approved):
        with self._lock:
            prior=self._prepared.get(intent_id)
            if prior is None or prior[0]!=request_id:
                fail("tool result belongs to a different request")
            if approved is not True:fail("tool result owner approval missing")
            confirmed=self._state.resolve(intent_id,approved=True,
                                           result_digest=result_sha256)
            return IntentProof(request_id,intent_id,confirmed["state"],
                               prior[1],confirmed["result_sha256"])

    def abort(self,*,request_id,intent_id):
        with self._lock:
            prior=self._prepared.get(intent_id)
            if prior is None or prior[0]!=request_id:
                fail("unbound tool intent abort")
            self._state.abort(intent_id)
            del self._prepared[intent_id]
