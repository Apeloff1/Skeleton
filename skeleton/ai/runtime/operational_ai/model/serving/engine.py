"""One synchronous serving path with identity, concurrency, cancellation and receipts."""
from __future__ import annotations
from dataclasses import replace
import time
from ..gateway import ModelGateway
from ..native import Generated
from .contracts import Request,ServingError,ModelIdentity,hash_bytes
from .model_slot import ModelSlot
from .receipts import Receipt
from .replay import fingerprint
from .output import safe_output
from .finish import finish_class
from .usage import UsageLedger
from .health import HealthWindow
from ...authority.budgets import Limits

class ServingEngine:
    def __init__(self,slot:ModelSlot,limits:Limits,usage:UsageLedger|None=None):
        self.slot=slot;self.limits=limits
        self.usage=usage or UsageLedger();self.health=HealthWindow()
        self.gateway=ModelGateway(slot.backend)

    def run(self,request:Request,expected:ModelIdentity,*,cancel=None)->tuple[Generated,Receipt]:
        if expected!=self.slot.fence.current:raise ServingError('wrong model epoch')
        if time.monotonic_ns()>=request.deadline_ns:raise ServingError('request expired')
        if request.max_tokens>self.limits.output_tokens:raise ServingError('request exceeds operator output ceiling')
        self.slot.fence.acquire(expected)
        try:
            with self.slot.slots.admitted(request.deadline_ns,cancel):
                if cancel is not None and cancel.is_set():raise ServingError('cancelled prior to inference')
                started=time.monotonic_ns()
                try:
                    result=self.gateway.complete(request.to_messages(),replace(self.limits,output_tokens=request.max_tokens),
                        seed=request.seed,temperature=request.temperature,cancel=cancel)
                    generated=result.generation
                    if (generated.generated_tokens>request.max_tokens or
                        time.monotonic_ns()>request.deadline_ns):
                        raise ServingError('native generation exceeded request bound')
                    safe_output(generated.text)
                    finish_class(generated.finish_reason)
                    receipt=Receipt(request.tenant,request.request_id,expected,
                        fingerprint(request,expected.model_sha256),
                        generated.output_digest,generated.prompt_tokens,
                        generated.generated_tokens,generated.finish_reason,
                        time.monotonic_ns()-started)
                    self.usage.charge(request.tenant,generated.prompt_tokens,generated.generated_tokens)
                    self.health.record(True)
                    return generated,receipt
                except BaseException:
                    self.health.record(False)
                    raise
        finally:self.slot.fence.release()
