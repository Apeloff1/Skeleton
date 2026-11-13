"""Couple real ExecutionSpine cancellation to registered active request fences."""
from __future__ import annotations
from .cancel_registry import CancellationRegistry
from .turn_bridge import TurnBridge
from .contracts import identifier,refuse

class CancellableTurn:
    def __init__(self,worker,registry=None):
        self.worker=worker
        self.registry=registry or CancellationRegistry()
        self.bridge=TurnBridge(worker)

    def turn(self,session_id,request_id,prompt,*,seed=0,temperature=0.8):
        session_id=identifier(session_id);request_id=identifier(request_id)
        cancel=self.registry.register(session_id,request_id,
                    deadline_ms=self.worker.spine.limits.deadline_ms)
        try:
            # The actual backend may be mid-GGUF generation when a caller
            # cancels. An isolated native worker + its own timeout is required
            # for a hard stop; this signal does not promise immediate kill.
            with self.bridge.guard.hold(self.bridge.identity.tenant,session_id,request_id):
                result=self.worker.turn(session_id,request_id,prompt,
                    seed=seed,temperature=temperature,cancellation=cancel)
            from .result_protocol import verify_turn_receipt
            return verify_turn_receipt(result,
                model_sha256=self.bridge.identity.model_sha256,
                tokenizer_sha256=self.bridge.identity.tokenizer_sha256)
        finally:
            self.registry.retire(session_id,request_id,cancel)
