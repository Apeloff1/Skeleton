"""Operational offline AI: one real inference, one authoritative chat commit.

Integrates the existing native chat engine, existing OfflineChatStore,
derived scoped memory, independent tool authorization, and integrity-chain
receipts. A model never gets implicit tool or storage write privileges.
"""
from __future__ import annotations
from dataclasses import dataclass
from contextlib import ExitStack
import time
import secrets
from typing import Any,TYPE_CHECKING
from ..authority.budgets import Limits,BudgetLedger
from ..authority.canonical import ContractViolation,digest,require_small_text
from ..authority.identity import Actor,require_id
from ..authority.grants import ToolGrant
from ..context.compiler import compile_context
from ..context.memory import MemoryStore
from ..context.sources import Source
from ..model.gateway import ModelGateway
from ..model.native import Generated
from ..persistence.journal import EventJournal
from ..tools.catalog import ToolCatalog
from ..tools.executor import ToolExecutor,ToolReceipt
from .session_locks import SessionLocks
from .custody.session import ProcessSessionFence

if TYPE_CHECKING:
    from skeleton.ai.model_runtime.offline_chat import OfflineChatStore


@dataclass(frozen=True, slots=True)
class AIReceipt:
    session_id:str
    request_id:str
    revision:int
    text:str
    output_digest:str
    model_digest:str
    tokenizer_digest:str
    prompt_tokens:int
    generated_tokens:int
    source_receipts:tuple[dict,...]
    replayed:bool
    audit_status:str

    def to_record(self)->dict:
        return {"session_id":self.session_id,"request_id":self.request_id,
                "revision":self.revision,"text":self.text,"output_digest":self.output_digest,
                "model_digest":self.model_digest,"tokenizer_digest":self.tokenizer_digest,
                "prompt_tokens":self.prompt_tokens,"generated_tokens":self.generated_tokens,
                "sources":list(self.source_receipts),"replayed":self.replayed,
                "audit_status":self.audit_status}


class OfflineAIService:
    """One product-oriented, owner-bound integration layer.

    Inferred memory is never stored automatically. Tool invocations require a
    separate, explicitly granted caller action; model output is plain text.
    The injected backend must perform real generation for product readiness.
    """

    def __init__(self,*,actor:Actor,gateway:ModelGateway,chat_store:"OfflineChatStore",
                 memory:MemoryStore,journal:EventJournal,catalog:ToolCatalog|None=None,
                 limits:Limits|None=None,process_fence:ProcessSessionFence|None=None):
        if (actor.model_digest!=gateway.backend.model_digest or
            actor.tokenizer_digest!=gateway.backend.tokenizer_digest):
            raise ContractViolation("service identity does not bind active model")
        self.actor=actor
        self.gateway=gateway
        self.store=chat_store
        self.memory=memory
        self.journal=journal
        self.catalog=catalog or ToolCatalog()
        self.tools=ToolExecutor(self.catalog,self.journal)
        self.limits=limits or Limits()
        self.session_locks=SessionLocks()
        self.process_fence=process_fence

    def create(self,*,system:str|None=None)->str:
        if system is not None:
            require_small_text(system,field="system instruction",maximum=8192)
        return self.store.create(self.actor.model_digest,self.actor.tokenizer_digest,system=system)

    def history(self,session:str)->dict[str,Any]:
        require_id(session,field="conversation")
        saved=self.store.load(session,self.actor.model_digest,self.actor.tokenizer_digest)
        return {"session_id":session,"revision":saved.revision,
                "messages":saved.transcript.to_list(),"model_digest":self.actor.model_digest}

    def admit_memory(self,source:Source,*,approved:bool=False)->dict:
        self.memory.admit(self.actor,source,approved=approved)
        self.journal.append(stream=source.source_id,event_id=f"memory_{source.revision}",
                            kind="memory.admitted",payload={"source":source.to_record(),
                            "approval_from_caller":True})
        return source.to_record()

    def forget_memory(self,source_id:str)->bool:
        deleted=self.memory.forget(self.actor,source_id)
        if deleted:
            self.journal.append(stream=source_id,event_id="memory_forget_"+secrets.token_hex(8),
                                kind="memory.forgotten",payload={"source_id":source_id})
        return deleted

    def _request_digest(self,session:str,question:str,*,seed:int,temperature:float)->str:
        return digest({"schema":"offline-ai-turn.v1","actor":self.actor.to_record(),
                       "session":session,"question":question,"limits":self.limits.to_record(),
                       "seed":seed,"temperature":float(temperature)})

    def _audit_commit(self,session:str,request_id:str,revision:int,
                      output_digest:str,request_digest:str)->str:
        event=self.journal.append(stream=session,event_id="ai_turn_"+request_id,
                 kind="ai.turn.committed",payload={"request_id":request_id,"revision":revision,
                 "output_digest":output_digest,"request_digest":request_digest,
                 "model_digest":self.actor.model_digest})
        return "replayed" if event.replayed else "recorded"

    def turn(self,*,session:str,request_id:str,question:str,seed:int=0,
             temperature:float=1.0)->AIReceipt:
        """Serialize same-process turns before reading durable replay state."""
        with ExitStack() as stack:
            stack.enter_context(self.session_locks.reserve(session,deadline_ms=self.limits.deadline_ms))
            if self.process_fence is not None:
                stack.enter_context(self.process_fence.reserve(session,deadline_ms=self.limits.deadline_ms))
            return self._turn_locked(session=session,request_id=request_id,
                                     question=question,seed=seed,temperature=temperature)

    def _turn_locked(self,*,session:str,request_id:str,question:str,seed:int=0,
                     temperature:float=1.0)->AIReceipt:
        require_id(session,field="conversation")
        require_id(request_id,field="request ID")
        if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in (session+request_id)):
            raise ContractViolation("offline store requires ASCII alphanumeric request/session IDs")
        require_small_text(question,field="user message",maximum=self.limits.input_bytes)
        signature=self._request_digest(session,question,seed=seed,temperature=temperature)
        saved=self.store.load(session,self.actor.model_digest,self.actor.tokenizer_digest)
        old=self.store.replay(session,request_id,signature)
        if old is not None:
            audit=self._audit_commit(session,request_id,old.revision,old.output_digest,signature)
            return AIReceipt(session,request_id,old.revision,old.text,old.output_digest,
                        self.actor.model_digest,self.actor.tokenizer_digest,
                        old.prompt_tokens,old.generated_tokens,(),True,audit)
        self.store.ensure_can_append(saved)
        hits=self.memory.search(self.actor,question,limit=max(1,self.limits.retrieval_hits))
        projection=compile_context(question,hits,self.limits)
        messages=saved.transcript.to_list()+[{"role":"user","content":projection.model_input}]
        completed=self.gateway.complete(messages,self.limits,seed=seed,temperature=temperature)
        generation=completed.generation
        if generation.model_digest!=self.actor.model_digest:
            raise ContractViolation("model switched during committed operation")
        transcript=saved.transcript.append("user",question).append("assistant",generation.text)
        receipt=self.store.commit(session=saved,request_id=request_id,request_digest=signature,
                     transcript=transcript,text=generation.text,output_digest=generation.output_digest,
                     prompt_tokens=generation.prompt_tokens,generated_tokens=generation.generated_tokens)
        audit=self._audit_commit(session,request_id,receipt.revision,receipt.output_digest,signature)
        return AIReceipt(session,request_id,receipt.revision,receipt.text,receipt.output_digest,
                         self.actor.model_digest,self.actor.tokenizer_digest,
                         receipt.prompt_tokens,receipt.generated_tokens,
                         projection.sources,bool(receipt.replayed),audit)

    def call_tool(self,*,session:str,invocation:str,name:str,args:dict,grant:ToolGrant)->ToolReceipt:
        self.store.load(session,self.actor.model_digest,self.actor.tokenizer_digest)
        ledger=BudgetLedger(self.limits)
        return self.tools.invoke(actor=self.actor,session=session,invocation=invocation,
                                 name=name,args=args,grant=grant,ledger=ledger)

    def status(self,session:str)->dict[str,Any]:
        """Report verified recovery state, not just a count of audit events."""
        require_id(session,field="conversation")
        # In production the OfflineChatStore exposes read_snapshot and SQL
        # custody. Lightweight contract fixtures can use count-only status;
        # that does NOT claim verified or release-ready operation.
        if hasattr(self.store,"read_snapshot"):
            from .recovery import inspect
            try:
                proof=inspect(self,session)
            except Exception as exc:
                return {"status":"audit-failed","reason":type(exc).__name__,"session":session}
            return {"status":"recoverable" if proof.status=="verified" else "audit-incomplete",
                    "session":session,"revision":proof.turns,"journal_head":proof.audit_head,
                    "missing_audits":proof.missing_audits,
                    "model_digest":self.actor.model_digest}
        saved=self.history(session)
        try:
            events=self.journal.replay(session)
            head=self.journal.head(session)
        except Exception as exc:
            return {"status":"audit-failed","reason":type(exc).__name__,"session":session}
        commits=sum(e.kind=="ai.turn.committed" for e in events)
        if commits!=saved["revision"]:
            return {"status":"audit-incomplete","session":session,"revision":saved["revision"],
                    "committed_audit_entries":commits,"journal_head":head[1]}
        return {"status":"recoverable","session":session,"revision":saved["revision"],
                "audit_events":len(events),"journal_head":head[1],
                "model_digest":self.actor.model_digest}
