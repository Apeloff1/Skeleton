"""Single admitted, real native turn with exact model and committed digest verification."""
from __future__ import annotations
from .identity import ActiveModel
from .result_protocol import verify_turn_receipt
from .contracts import identifier,utf8,nonnegative,number,refuse
from .once_guard import OnceGuard

class TurnBridge:
    def __init__(self,supervisor,guard=None):
        self.worker=supervisor
        self.guard=guard or OnceGuard()
        self.identity=ActiveModel.from_supervisor(supervisor)

    def turn(self,session_id,request_id,prompt,*,seed=0,temperature=0.8):
        session_id=identifier(session_id);request_id=identifier(request_id)
        question=utf8(prompt,maximum=self.worker.spine.limits.input_bytes)
        seed=nonnegative(seed,maximum=2**32-1)
        temperature=number(temperature,minimum=0.000000001,maximum=2)
        with self.guard.hold(self.identity.tenant,session_id,request_id):
            result=self.worker.turn(session_id,request_id,question,
                                    seed=seed,temperature=temperature)
            verified=verify_turn_receipt(result,model_sha256=self.identity.model_sha256,
                                         tokenizer_sha256=self.identity.tokenizer_sha256)
            return verified
