"""Concrete authenticated operations over the existing real production supervisor.

No fake model results, no alternative conversation database, and no automatic
retry of uncertain inference. Each real turn calls SupervisedAI.turn once.
"""
from __future__ import annotations
import secrets
from .contracts import exact,refuse,canonical
from .identity import ActiveModel
from .inputs import normalize
from .operations import schema
from .result_protocol import verify_turn_receipt

class LaptopDispatcher:
    def __init__(self,worker):
        if worker is None or not hasattr(worker,"spine") or not hasattr(worker,"turn"):
            refuse("production supervisor required")
        self.worker=worker
        self.active=ActiveModel.from_supervisor(worker)
        self.limits=worker.spine.limits

    def dispatch(self,operation,payload):
        data=normalize(operation,payload,self.limits)
        if operation=="create":
            session="s_"+secrets.token_hex(16)
            self.worker.spine.create(session)
            return {"session_id":session,
                    "model_sha256":self.active.model_sha256}
        if operation=="turn":
            result=self.worker.turn(data["session_id"],data["request_id"],
                data["prompt"],seed=data.get("seed",0),
                temperature=data.get("temperature",0.8))
            result=verify_turn_receipt(result,
                model_sha256=self.active.model_sha256,
                tokenizer_sha256=self.active.tokenizer_sha256)
            # The authoritative receipt comes from the existing SQLite spine;
            # never fabricate a result if generation failed or timed out.
            return {"receipt":result}
        if operation=="history":
            history=self.worker.spine.history(data["session_id"])
            if not isinstance(history,(tuple,list)):
                refuse("invalid authoritative history")
            return {"session_id":data["session_id"],"messages":list(history)}
        if operation=="replay":
            result=self.worker.spine.replay(data["session_id"],data["request_id"],
                data["prompt"],seed=data.get("seed",0),
                temperature=data.get("temperature",0.8))
            return {"replay":result,"found":result is not None}
        if operation=="close":
            return {"closed":self.worker.spine.close(data["session_id"])}
        if operation=="status":
            return {"status":self.worker.status(),"model_sha256":self.active.model_sha256}
        if operation=="doctor":
            return {"doctor":self.worker.spine.health(),"release_certified":False}
        if operation=="identity":
            return {"identity":self.active.to_record(),"release_certified":False}
        if operation=="outbox_pending":
            return {"events":list(self.worker.spine.pending_events(limit=data.get("limit",16)))}
        if operation=="outbox_ack":
            return {"acknowledged":self.worker.spine.acknowledge_event(
                data["event_key"],data["event_sha256"])}
        refuse("unreachable unapproved operation")

    def protocol(self):
        return schema()
