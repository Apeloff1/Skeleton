"""Strict contract-only test double; NEVER presented as a native inference model.

Its sole purpose is testing the public API's input checks, receipt guards,
framing and replay wiring without consuming GGUF resources.
"""
from __future__ import annotations
import hashlib
from types import SimpleNamespace

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import refuse

MODEL="a"*64
TOKENIZER="b"*64
OUTPUT="hello"
OUTPUT_SHA=hashlib.sha256(OUTPUT.encode()).hexdigest()

class _Backend:
    model_digest=MODEL
    tokenizer_digest=TOKENIZER

class _Spine:
    def __init__(self):
        self.identity=SimpleNamespace(tenant="local",subject="owner",
            model_sha256=MODEL,tokenizer_sha256=TOKENIZER)
        self.backend=_Backend()
        self.limits=SimpleNamespace(input_bytes=32768,response_bytes=131072,
            max_output_tokens=128,context_tokens=2048,deadline_ms=60000,
            max_pending=16,max_history=128,max_sources=6)
        self.created=set()
        self.closed=set()
        self.receipts={}
        self.acknowledged=set()

    def create(self,session):
        if session in self.created:raise ValueError("duplicate test session")
        self.created.add(session)
        return session

    def close(self,session):
        if session not in self.created:raise ValueError("unknown test session")
        if session in self.closed:return False
        self.closed.add(session);return True

    def history(self,session):
        if session not in self.created:raise ValueError("unknown test session")
        return tuple({"role":"user","content":"contract-only-example"} for _ in range(1))

    def replay(self,session,request_id,prompt,*,seed=0,temperature=0.8):
        record=self.receipts.get((session,request_id,prompt,seed,temperature))
        return None if record is None else {**record,"replayed":True}

    def health(self):
        return {"state":"contract-test-double-only","integrity_checked":False}

    def pending_events(self,limit=16):
        return tuple([{"event_key":"e_1","event_sha256":OUTPUT_SHA}][:limit])

    def acknowledge_event(self,key,sha):
        if key!="e_1" or sha!=OUTPUT_SHA:raise ValueError("unknown test outbox event")
        if key in self.acknowledged:return False
        self.acknowledged.add(key);return True

class FakeWorker:
    def __init__(self):
        self.spine=_Spine()
        self.generation_calls=0

    def turn(self,session,request_id,prompt,*,seed=0,temperature=0.8,cancellation=None):
        if session not in self.spine.created or session in self.spine.closed:
            raise ValueError("unknown or closed session")
        key=(session,request_id,prompt,seed,temperature)
        prior=self.spine.receipts.get(key)
        if prior:return {**prior,"replayed":True}
        # Mirror the production SQLite request-identity CAS: once the
        # (session, request ID) pair commits, changed prompt or sampler
        # parameters can NEVER issue a second native forward pass. This fake
        # deliberately does not infer real device or source-rights approval.
        for committed_session,committed_id,*_ in self.spine.receipts:
            if committed_session==session and committed_id==request_id:
                refuse("native request identity already committed with different input")
        self.generation_calls+=1
        result={"schema":"test-double-receipt-not-model-evidence",
                "model_sha256":MODEL,"tokenizer_sha256":TOKENIZER,
                "output_sha256":OUTPUT_SHA,"text":OUTPUT,
                "prompt_tokens":2,"generated_tokens":1,"replayed":False}
        self.spine.receipts[key]=result
        return dict(result)

    def status(self):
        return {"capacity":{"active":0,"maximum":1},
                "model_circuit":{"state":"test-double"},
                "metrics":{"calls":self.generation_calls}}
