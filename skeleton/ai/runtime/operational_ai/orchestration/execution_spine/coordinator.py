"""Production-oriented orchestration: one real inference per admitted request.

The session lock spans context assembly, native inference and atomic commit.
If a crash occurs after native inference but before commit the pending request
is held until explicitly recovered; no automatic double-generation or tool use.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable,Callable,Any
import time
from .contracts import Identity,InferenceRequest,SpineLimits,SpineError,Cancelled,Conflict,Busy
from .database import SpineDatabase
from .principal import create_session,close_session,require_session
from . import requests,receipts,history,outbox
from .context import Evidence,compile_projection
from .window import plan
from .citation_guard import audit_citations
from .token_admission import inspect_token_budget
from .capacity import prepare_context
from .capacity.proofs import describe_decision
from .adapter import generate,RealBackend
from .lease import SessionGate
from .cancellation import Cancellation
from .chain import verify
from .doctor import inspect

class ExecutionSpine:
    def __init__(self,*,db:SpineDatabase,session_gate:SessionGate,
                 backend:RealBackend,identity:Identity,limits:SpineLimits|None=None,
                 evidence_provider:Callable[[Identity,str],Iterable[Evidence]]|None=None):
        if backend.model_digest!=identity.model_sha256 or backend.tokenizer_digest!=identity.tokenizer_sha256:
            raise SpineError('actual backend and subject model custody mismatch')
        self.db=db;self.session_gate=session_gate;self.backend=backend
        self.identity=identity;self.limits=limits or SpineLimits()
        self.evidence_provider=evidence_provider

    def create(self,session:str):
        with self.db.transaction() as conn:
            create_session(conn,self.identity,session)
        return session

    def close(self,session:str)->bool:
        with self.session_gate.hold(session,deadline_ms=self.limits.deadline_ms):
            with self.db.transaction() as conn:
                return close_session(conn,self.identity,session)

    def history(self,session:str)->tuple[dict,...]:
        with self.db.snapshot() as conn:
            return history.load(conn,self.identity,session,self.limits)

    def turn(self,session:str,request_id:str,prompt:str,*,seed:int=0,
             temperature:float=0.8,cancellation:Cancellation|None=None)->dict:
        req=InferenceRequest(self.identity,session,request_id,prompt,seed,temperature)
        cancel=cancellation or Cancellation(deadline_ms=self.limits.deadline_ms)
        cancel.check()
        with self.session_gate.hold(session,deadline_ms=cancel.remaining_ms()):
            # Check idempotent replay *before* preparing a fresh context: a
            # committed result is authoritative even if sources were later
            # deleted, the model changed its tokenizer implementation, or the
            # current context ceiling was tightened.
            with self.db.snapshot() as conn:
                replay=receipts.replay(conn,req)
                if replay is not None:return replay
                saved=history.load(conn,self.identity,session,self.limits)
            # Context admission is entirely read-only and MUST precede durable
            # request reservation. A malformed source or an overlong prompt
            # cannot strand an inference lease before the model even starts.
            cancel.check()
            evidence=self.evidence_provider(self.identity,prompt) if self.evidence_provider else ()
            prepared=prepare_context(identity=self.identity,backend=self.backend,
                history=saved,prompt=prompt,evidence=evidence,limits=self.limits)
            cancel.check()
            # A backend that owns an isolated native process can reject
            # resource pressure BEFORE a durable lease is reserved. Unknown
            # telemetry remains a hold; existing backends without such a gate
            # retain their previous (less-qualified) admission semantics.
            resource_gate=getattr(self.backend,'admit_before_reservation',None)
            if callable(resource_gate):
                resource_gate()
            cancel.check()
            with self.db.transaction() as conn:
                available=requests.reserve(conn,req,self.limits,
                    lease_ns=self.limits.deadline_ms*1_000_000)
                if available['state']=='committed':
                    return receipts.replay(conn,req) or (_ for _ in ()).throw(Conflict('lost committed receipt'))
                token=available['token']
            # Native inference is the only speculative operation after reserve.
            # An exception must leave the pending request held rather than
            # guessing whether execution was completed by the backend.
            generated=generate(self.backend,self.identity,prepared.messages,self.limits,
                               seed=seed,temperature=float(temperature))
            cancel.check()
            citation_review=audit_citations(generated.text,prepared.sources)
            with self.db.transaction() as conn:
                if prepared.sources and self.evidence_provider is not None:
                    fence=getattr(self.evidence_provider,'require_current',None)
                    if callable(fence):
                        fence(conn,prepared.sources)
                result=receipts.commit(conn,req,self.limits,generated,token,
                    context_sha256=prepared.projection.context_sha256,
                    source_receipts=prepared.sources,
                    omitted_turns=prepared.omitted_turns,
                    capacity_report=describe_decision(prepared))
            return result | {'text':generated.text,
                             'context_sha256':prepared.projection.context_sha256,
                             'evidence_sources':len(prepared.sources),
                             'omitted_context_turns':prepared.omitted_turns,
                             'omitted_evidence_sources':prepared.omitted_sources,
                             'citation_review':citation_review}

    def replay(self,session:str,request_id:str,prompt:str,*,seed:int=0,temperature:float=0.8)->dict|None:
        req=InferenceRequest(self.identity,session,request_id,prompt,seed,temperature)
        with self.db.snapshot() as conn:
            require_session(conn,self.identity,session)
            return receipts.replay(conn,req)

    def pending_events(self,limit:int=32)->tuple[dict,...]:
        with self.db.snapshot() as conn:return outbox.pending(conn,limit=limit)

    def acknowledge_event(self,key:str,event_sha256:str)->bool:
        with self.db.transaction() as conn:return outbox.acknowledge(conn,key,event_sha256)

    def health(self)->dict:return inspect(self.db)
