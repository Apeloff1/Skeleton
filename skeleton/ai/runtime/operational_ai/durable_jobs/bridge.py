"""Real native AI work dispatch, bounded by the durable work claim.

No generated reply is fabricated. The injected OfflineAIService owns actual
checkpoint/tokenizer inference, chat commit, recovery and source memory.
"""
from __future__ import annotations

from .canonical import sha256, require_sha
from .errors import deny
from .result import JobResult
from .spec import JobIdentity
from .store import JobStore, ClaimedJob


class NativeJobBridge:
    """Execute exactly the committed job's session and request identity.

    A model's output is always untrusted text. This bridge does not execute
    model-authored tools or produce any external side effect.
    """

    def __init__(self,service,store:JobStore):
        if not callable(getattr(service,"turn",None)) or not hasattr(service,"actor"):
            deny("bridge-native-service-required")
        if type(store) is not JobStore:
            deny("bridge-store")
        self.service=service
        self.store=store

    def _bind(self,claim:ClaimedJob):
        actor=self.service.actor
        identity=claim.owner
        if (identity.tenant!=actor.tenant or identity.user!=actor.user or
            identity.model_sha256!=actor.model_digest or
            identity.tokenizer_sha256!=actor.tokenizer_digest):
            deny("bridge-principal-or-model-mismatch")

    def run_one(self,worker_id:str,*,clock_ms,target_job_id:str|None=None):
        """Read a trusted wall clock both before and after native inference.

        The finite lease must remain active after real generation. A slow model
        may expire its lease; such a result is NOT automatically accepted.
        """
        from .canonical import require_int
        if not callable(clock_ms):
            deny("bridge-clock-required")
        started=require_int(clock_ms(),0,2**63-1,"clock")
        claim=self.store.claim(worker_id,now_ms=started,target_job_id=target_job_id)
        if claim is None:
            return None
        try:
            self._bind(claim)
            receipt=self.service.turn(
                session=claim.owner.session,
                request_id=claim.request_id,
                question=claim.question,
            )
            if (receipt.session_id!=claim.owner.session or
                receipt.request_id!=claim.request_id or
                receipt.model_digest!=claim.owner.model_sha256 or
                receipt.tokenizer_digest!=claim.owner.tokenizer_sha256):
                deny("bridge-receipt-identity")
            result=JobResult(
                text=receipt.text,
                output_sha256=sha256(receipt.text.encode("utf-8")),
                model_sha256=receipt.model_digest,
                tokenizer_sha256=receipt.tokenizer_digest,
                prompt_tokens=receipt.prompt_tokens,
                generated_tokens=receipt.generated_tokens,
                original_request_id=receipt.request_id,
            )
            finished=require_int(clock_ms(),0,2**63-1,"clock")
            self.store.finish(claim,result,now_ms=finished)
            return result
        except Exception:
            # Any failure after a native request might be post-commit. Mark
            # ambiguous, never automatically attempt a second generation.
            try:
                finished=require_int(clock_ms(),0,2**63-1,"clock")
                self.store.fail(claim,now_ms=finished,code="native-ambiguous",
                                ambiguous=True)
            except Exception:
                pass  # Stale/expired claim remains untrusted; sweep will hold.
            raise
