"""Composable offline inference/retrieval/citation plan without synthetic answers.

All generation is delegated to the existing supervised GGUF execution path,
which alone owns the authoritative SQLite transcript and result receipts.
"""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import Scope,identifier,integer,text,sha,refuse
from .retrieval import BM25
from .planner import PlanTask,compile_plan
from .contexts import ContextSlice,pack
from .receipts import from_supervisor
from .metrics import Metrics
class CognitiveEngine:
    def __init__(self,scope,supervisor,*,metrics=None):
        if type(scope) is not Scope:refuse("canonical model/tenant scope required")
        if supervisor is None or not callable(getattr(supervisor,"turn",None)):
            refuse("real supervised GGUF runtime required")
        self._assert_worker_scope(supervisor,scope)
        self.scope=scope;self.supervisor=supervisor
        self.metrics=metrics if metrics is not None else Metrics()
        self.metrics_dropped=0

    @staticmethod
    def _assert_worker_scope(supervisor,scope):
        """Require matching active native backend before generating output."""
        try:
            identity=supervisor.spine.identity
            backend=supervisor.spine.backend
            active=(identity.tenant,identity.subject,identity.model_sha256,
                    identity.tokenizer_sha256)
            native=(backend.model_digest,backend.tokenizer_digest)
        except (AttributeError,TypeError):
            refuse("canonical native worker backend absent")
        wanted=(scope.tenant,scope.subject,scope.model_sha256,scope.tokenizer_sha256)
        if active!=wanted or native!=wanted[2:]:
            refuse("native worker principal/model/tokenizer scope disagrees")
        return True
    def plan(self,*,prompt,context_slices,window,output_tokens):
        prompt=text(prompt)
        integer(window,minimum=128,maximum=262144)
        integer(output_tokens,minimum=1,maximum=8192)
        admitted=pack(context_slices,window=window,output_reserved=output_tokens)
        steps=(PlanTask("retrieval",1000,0,"retrieval",()),
               PlanTask("context",500,0,"memory",("retrieval",)),
               PlanTask("generate",10000,output_tokens,"model",("context",)),
               PlanTask("verify",500,0,"verification",("generate",)))
        pipeline=compile_plan(steps,max_tokens=window)
        return {"context":admitted,"plan":pipeline,
                "actual_native_token_count":False,
                "native_generation_already_performed":False}
    def turn(self,session_id,request_id,prompt,*,seed=0,temperature=0.8):
        from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
            identifier as require_id,nonnegative,number)
        require_id(session_id);require_id(request_id)
        prompt=text(prompt)
        nonnegative(seed,maximum=2**32-1)
        number(temperature,minimum=1e-9,maximum=2)
        self._assert_worker_scope(self.supervisor,self.scope)
        # No generation retry or hosted fallback here.
        result=self.supervisor.turn(session_id,request_id,prompt,
                                    seed=seed,temperature=temperature)
        receipt=from_supervisor(self.scope,session_id,request_id,result)
        # Native state has already committed: diagnostic overflow cannot become
        # a false failed turn and invite another generation attempt.
        try:
            self.metrics.observe("native_turn","replayed" if receipt.replayed else "accepted",0)
        except Exception:
            self.metrics_dropped=min(2**53-1,self.metrics_dropped+1)
        return receipt
