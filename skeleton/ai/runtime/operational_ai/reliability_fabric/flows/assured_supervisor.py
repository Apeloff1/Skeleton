"""Source-bound preflight to actual native supervisor with irreversible-effect holds.

Production SupervisedAI/SQLite remain canonical. Uncertain execution never
triggers an automatic retry or a speculative quota refund.
"""
from __future__ import annotations
from threading import RLock
from .quota import Quota
from .rate_window import RateWindow
from .circuit import Circuit
from .preflight import inspect
from .native_turn import complete, replay_only
from ..contracts import fail
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    identifier,utf8,nonnegative,number)

class AssuredSupervisor:
    def __init__(self,worker,*,tenant_token_cap=65536,
                 global_token_cap=262144,rate_per_window=32,failure_ceiling=4):
        if worker is None or not hasattr(worker,"spine") or not callable(getattr(worker,"turn",None)):
            fail("real production SupervisedAI required")
        self.worker=worker
        self.quota=Quota(tenant_ceiling=tenant_token_cap,global_ceiling=global_token_cap)
        self.rate=RateWindow(max_calls=rate_per_window)
        self.circuit=Circuit(failure_ceiling=failure_ceiling)
        self._lock=RLock()
        self._inflight=set()

    def execute(self,evidence,*,session_id,request_id,prompt,seed=0,temperature=0.8):
        identity=self.worker.spine.identity
        session_id=identifier(session_id)
        request_id=identifier(request_id)
        prompt=utf8(prompt,maximum=self.worker.spine.limits.input_bytes)
        seed=nonnegative(seed,maximum=2**32-1)
        temperature=number(temperature,minimum=0.000000001,maximum=2)
        key=(identity.tenant,session_id,request_id)
        with self._lock:
            if key in self._inflight:fail("concurrent duplicate native request")
            self._inflight.add(key)
        try:
            inspect(self.worker,evidence)
            self.circuit.admit()
            self.rate.admit(identity.tenant)
            prior=replay_only(self.worker,session_id=session_id,request_id=request_id,
                              prompt=prompt,seed=seed,temperature=temperature)
            if prior["found"]:
                return {"status":"durable-replayed","generated":False,
                        "receipt":prior["receipt"],"charged_tokens":0}
            self.quota.reserve(identity.tenant,request_id,
                 prompt=self.worker.spine.limits.context_tokens,
                 output=self.worker.spine.limits.max_output_tokens)
            try:
                output=complete(self.worker,evidence,session_id=session_id,
                                request_id=request_id,prompt=prompt,
                                seed=seed,temperature=temperature)
                receipt=output["receipt"]
                if receipt["replayed"]:
                    fail("replay after fresh reservation requires durable reconciliation")
                charged=self.quota.commit(identity.tenant,request_id,
                       prompt=receipt["prompt_tokens"],
                       output=receipt["generated_tokens"])
                self.circuit.success()
                return {"status":"native-committed","generated":True,
                        "receipt":receipt,"assurance":output["assurance"],
                        "charged_tokens":charged["charged_tokens"]}
            except BaseException:
                self.circuit.failure()
                raise
        finally:
            with self._lock:self._inflight.discard(key)

    def status(self):
        with self._lock:
            return {"inflight":len(self._inflight),
                    "quota":self.quota.snapshot(),
                    "circuit":self.circuit.snapshot(),
                    "native_e2e_certified":False,"release_certified":False}
