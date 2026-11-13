"""Single application dispatch surface; model responses cannot invoke tools."""
from __future__ import annotations
from typing import Any
from ..authority.canonical import ContractViolation,require_small_text
from ..authority.identity import require_id
from ..orchestration.service import OfflineAIService


class Dispatcher:
    def __init__(self,service:OfflineAIService):
        self.service=service

    @staticmethod
    def _shape(data:dict,required:set[str],optional:set[str]=frozenset()):
        if not isinstance(data,dict) or not required.issubset(data) or set(data)-required-optional:
            raise ContractViolation("operation payload has missing or unknown fields")

    def dispatch(self,operation:str,payload:dict)->dict[str,Any]:
        if operation=="create":
            self._shape(payload,set(),{"system"})
            return {"session_id":self.service.create(system=payload.get("system"))}
        if operation=="turn":
            self._shape(payload,{"session_id","request_id","question"},{"seed","temperature"})
            receipt=self.service.turn(session=payload["session_id"],
                request_id=payload["request_id"],question=payload["question"],
                seed=payload.get("seed",0),temperature=payload.get("temperature",1.0))
            return {"receipt":receipt.to_record()}
        if operation=="history":
            self._shape(payload,{"session_id"})
            return self.service.history(payload["session_id"])
        if operation=="status":
            self._shape(payload,{"session_id"})
            return self.service.status(payload["session_id"])
        if operation=="memory_search":
            self._shape(payload,{"question"},{"limit"})
            limit=payload.get("limit",8)
            hits=self.service.memory.search(self.service.actor,payload["question"],limit=limit)
            return {"hits":[{"source_id":h.source_id,"sha256":h.sha256,"score":h.score,
                            "source_start":h.start,"source_end":h.end,"passage":h.body,
                            "trust":h.trust,"origin":h.origin} for h in hits]}
        raise ContractViolation("unknown local API operation")
