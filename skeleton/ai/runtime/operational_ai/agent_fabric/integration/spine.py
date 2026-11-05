"""Use existing real ExecutionSpine for model work; no alternate inference engine."""
from __future__ import annotations
from ..core.errors import Integrity
from ..core.canonical import hex_digest
class SpinePort:
    def __init__(self,spine):
        if not callable(getattr(spine,'turn',None)) or not hasattr(spine,'identity'):
            raise Integrity('authoritative ExecutionSpine required')
        self.spine=spine
    def complete(self,*,session,request_id,prompt,seed=0,temperature=.8):
        result=self.spine.turn(session,request_id,prompt,seed=seed,temperature=temperature)
        if not isinstance(result,dict) or result.get('model_sha256')!=self.spine.identity.model_sha256:
            raise Integrity('model port identity does not match authoritative receipt')
        if result.get('tokenizer_sha256')!=self.spine.identity.tokenizer_sha256:
            raise Integrity('model port tokenizer changed')
        hex_digest(result.get('output_sha256'),'model output')
        return result
