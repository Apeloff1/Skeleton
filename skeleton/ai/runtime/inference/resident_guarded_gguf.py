"""Trusted startup binding of one native resident GGUF child to canonical guard.

Private session has no slot cache, no operator bypass, no network transport,
and exact server tokenizer round trips. Only text protocol is advertised.
"""
from __future__ import annotations
import hashlib
import json
import secrets
import threading
import time
from dataclasses import asdict

from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.provider_runtime import ProviderPolicyError
from .guarded_composition import ProtectedLocalComponents, compose_protected_local_adapter
from .local import LocalInferenceRequest, LocalInferenceResult, LocalInferenceCancelled, LocalInputBudget, LocalPreparedInput, LocalInferenceEngine
from .resident_gguf_batch import ResidentGGUFBatch
from .llama_cpp import LlamaCppRuntimeError


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


class ResidentGuardedGGUF:
    model_family="gguf_open_weight"
    protocol_capabilities=("text-generation",)
    tokenizer_kind="resident_exact_native_tokenizer"

    def __init__(self,session: ResidentGGUFBatch):
        if not isinstance(session,ResidentGGUFBatch):
            raise TypeError("resident native session required")
        with session._lock:
            if not session._ready.is_set() or session._closed or session._batches or session._spill_temp or session._guarded_owner is not None:
                raise ProviderPolicyError("fresh private no-spill resident session required")
            session._assert_source()
            self._session=session
            self._issuer=object()
            self._slots=threading.BoundedSemaphore(session._policy.slots)
            self.model_id=session._model.model_id
            self._model_id=self.model_id
            self._model_digest=session._model.model_digest
            self._runtime_digest=digest({"schema":"skeleton.resident.gguf.guarded.v1",
                "server":session._server.sha256,"model":self._model_digest,
                "profile":asdict(session._policy),"libraries":list(session._pins),
                "cli_profile":session._model.execution_profile_digest,
                "session":secrets.token_hex(16)})
            self._tokenizer_digest=digest({"model":self._model_digest,"runtime":self._runtime_digest,
                                           "special_tokens":False,"renderer":"canonical"})
            session._guarded_owner=self._issuer

    @property
    def model_digest(self):
        return self._model_digest

    @property
    def runtime_digest(self):
        return self._runtime_digest

    def check_readiness(self):
        s=self._session
        if (s._closed or not s._ready.is_set() or s._proc is None or s._proc.poll() is not None
            or s._guarded_owner is not self._issuer or self.model_id!=self._model_id
            or time.monotonic()>=s._deadline):
            raise LlamaCppRuntimeError("guarded resident native session is unavailable")

    def assert_identity(self):
        self.check_readiness()
        self._session._assert_source()
        if self._session._model.model_digest!=self._model_digest:
            raise LlamaCppRuntimeError("resident model identity drift")

    def _declared_generation_limits(self):
        context=self._session._policy.context_per_slot
        return {"context_window":context,"max_total_tokens":context,
                "max_output_tokens":min(context-1,8192),"shared_context":True,
                "tokenizer":self.tokenizer_kind,"max_output_utf8_bytes":4*1024**2,
                "limits_source":"pinned_resident_native_backend"}

    def generation_limits(self):
        self.check_readiness()
        return self._declared_generation_limits()

    def _deadline(self):
        return min(self._session._deadline,time.monotonic()+self._session._policy.timeout_seconds)

    def encode(self,text):
        self.check_readiness()
        if not isinstance(text,str) or not text or len(text.encode())>1024**2:
            raise ValueError("bounded resident tokenizer text required")
        reply=self._session._call("/tokenize",{"content":text,"add_special":False,"parse_special":False},deadline=self._deadline())
        ids=reply.get("tokens") if isinstance(reply,dict) else None
        if not isinstance(ids,list) or not 1<=len(ids)<=self._session._policy.context_per_slot or any(type(t) is not int or not 0<=t<=2**31-1 for t in ids):
            raise LlamaCppRuntimeError("resident exact tokenizer response invalid")
        return tuple(ids)

    def decode(self,tokens):
        self.check_readiness()
        if not 1<=len(tokens)<=self._session._policy.context_per_slot or any(type(t) is not int or not 0<=t<=2**31-1 for t in tokens):
            raise ValueError("resident exact detokenizer IDs invalid")
        reply=self._session._call("/detokenize",{"tokens":list(tokens)},deadline=self._deadline())
        text=reply.get("content") if isinstance(reply,dict) else None
        if not isinstance(text,str) or len(text.encode())>1024**2:
            raise LlamaCppRuntimeError("resident exact detokenizer response invalid")
        return text

    def prepare_input(self,request,*,scope_digest=None):
        self.assert_identity()
        if not isinstance(request,LocalInferenceRequest) or request.tools or request.structured_output_schema is not None or request.tool_choice in {"required","specific"}:
            raise ProviderPolicyError("resident guard supports text generation only")
        source=request.rendered_input
        budget=LocalInputBudget.from_limits(self._declared_generation_limits())
        budget.validate_request(request,0,rendered=source)
        ids=self.encode(source)
        if self.decode(ids)!=source:
            raise ProviderPolicyError("native tokenizer roundtrip changed authorized input")
        budget.validate_tokens(len(ids),request.max_output_tokens)
        pin=hashlib.sha256(source.encode()).hexdigest()
        seq=TokenSequence(self._tokenizer_digest,ids,pin)
        return LocalPreparedInput(request_digest=request.digest,model_digest=self.model_digest,
            runtime_digest=self.runtime_digest,execution_profile_digest=None,tokenizer_digest=self._tokenizer_digest,
            source_digest=pin,sequence_digest=seq.digest,input_tokens=len(ids),scope_digest=scope_digest,
            token_sequence=seq,issuer=self._issuer)

    def count_input_tokens(self,request):
        return self.prepare_input(request).input_tokens

    def validate_prepared_input(self,request,prepared):
        self.assert_identity()
        if not isinstance(prepared,LocalPreparedInput):
            raise ProviderPolicyError("resident prepared input required")
        pin=hashlib.sha256(request.rendered_input.encode()).hexdigest()
        prepared.assert_binding(request,issuer=self._issuer,model_digest=self.model_digest,
            runtime_digest=self.runtime_digest,execution_profile_digest=None,tokenizer_digest=self._tokenizer_digest,
            source_digest=pin)
        seq=prepared.token_sequence
        if (not isinstance(seq,TokenSequence) or seq.digest!=prepared.sequence_digest
            or seq.tokenizer_digest!=self._tokenizer_digest or seq.source_text_digest!=pin
            or len(seq.token_ids)!=prepared.input_tokens or self.decode(seq.token_ids)!=request.rendered_input):
            raise ProviderPolicyError("resident prepared sequence changed")
        LocalInputBudget.from_limits(self._declared_generation_limits()).validate_tokens(prepared.input_tokens,request.max_output_tokens)

    def infer(self,request,cancel):
        # The engine must carry the preflight pinned token sequence; direct
        # unprepared inference is deliberately unsupported for this backend.
        raise ProviderPolicyError("guarded resident inference requires prepared input")

    def infer_prepared(self,request,cancel,prepared):
        if not isinstance(cancel,threading.Event) or cancel.is_set():
            raise LocalInferenceCancelled("resident generation cancelled")
        self.validate_prepared_input(request,prepared)
        if not self._slots.acquire(blocking=False):
            raise LlamaCppRuntimeError("resident native slot capacity exhausted")
        start=time.monotonic()
        try:
            self.check_readiness()
            if cancel.is_set():
                raise LocalInferenceCancelled("resident generation cancelled")
            reply=self._session._call("/completion",{
                "prompt":list(prepared.token_sequence.token_ids),"n_predict":request.max_output_tokens,
                "stream":False,"cache_prompt":False,"return_tokens":True,
                "temperature":request.temperature,"seed":request.seed%(2**32-1),
                "top_k":request.top_k,"top_p":request.top_p,"min_p":request.min_p,
                "repeat_penalty":request.repetition_penalty,"stop":list(request.stop)},deadline=self._deadline())
            if cancel.is_set():
                raise LocalInferenceCancelled("resident result withheld after cancellation")
            if not isinstance(reply,dict) or reply.get("truncated") is not False or reply.get("stop_type") not in {"eos","limit","word"}:
                raise LlamaCppRuntimeError("resident guarded completion receipt invalid")
            text,ids=reply.get("content"),reply.get("tokens")
            if (not isinstance(text,str) or len(text.encode())>4*1024**2 or not isinstance(ids,list)
                or len(ids)>request.max_output_tokens or any(type(t) is not int or not 0<=t<=2**31-1 for t in ids)
                or reply.get("tokens_evaluated")!=prepared.input_tokens):
                raise LlamaCppRuntimeError("resident output or native input accounting invalid")
            self.assert_identity()
            proof=digest({"request":request.digest,"source":prepared.sequence_digest,
                "runtime":self.runtime_digest,"response":hashlib.sha256(text.encode()).hexdigest(),
                "output_ids":ids,"stop":reply["stop_type"]})
            return LocalInferenceResult(text,self.model_id,self.model_digest,prepared.input_tokens,len(ids),
                finish_reason="length" if reply["stop_type"]=="limit" else "completed",
                response_id="local-resident:"+proof,execution_receipt_digest=proof,
                latency_ms=(time.monotonic()-start)*1000)
        finally:
            # The engine's worker retains this slot until the real HTTP call
            # returns. Cancelled clients cannot start additional native work.
            self._slots.release()


def build_guarded_resident_adapter(session,*,snapshots,reviewer,max_queue_size=64):
    """Trusted application composition; no unguarded fallback."""
    if not callable(getattr(snapshots,"resolve",None)) or not callable(reviewer):
        raise ProviderPolicyError("independent snapshot/reviewer authorities required")
    backend=ResidentGuardedGGUF(session)
    encode,decode=backend.encode,backend.decode
    def verify(active,encoder,decoder):
        if active is not backend or encoder is not encode or decoder is not decode:
            return False
        try:
            backend.assert_identity()
            return True
        except Exception:
            return False
    components=ProtectedLocalComponents(snapshots=snapshots,reviewer=reviewer,
        tokenize=encode,detokenize=decode,verify_native_tokenizer=verify,
        sampler_support=lambda *_:False,projection_attestor=lambda *_:False)
    try:
        engine=LocalInferenceEngine(backend,cache_size=0,max_concurrency=session._policy.slots,
            max_batch_size=session._policy.slots,max_queue_size=max_queue_size,require_guarded_context=True)
        return compose_protected_local_adapter(engine,components=components,
            artifact_status={"schema":"skeleton.resident.gguf.guarded.v1","model_id":backend.model_id,
                "model_digest":backend.model_digest,"runtime_digest":backend.runtime_digest,
                "tokenizer_digest":backend._tokenizer_digest})
    except BaseException:
        session.close()
        raise
